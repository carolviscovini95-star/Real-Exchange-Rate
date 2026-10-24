"""FIN 470: bilateral real exchange rates using monthly IMF data."""
from __future__ import annotations

from datetime import date
from io import StringIO

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pycountry
import requests
import streamlit as st

BASE = "https://api.imf.org/external/sdmx/3.0"
FIRST = "1976-01"
META_ACCEPT = "application/vnd.sdmx.structure+json;version=2.0.0"
CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=2.0.0"


class DataError(Exception):
    """An actionable data retrieval or interpretation problem."""


def get_response(path, accept, params=None):
    url = BASE + path
    try:
        r = requests.get(url, headers={"Accept": accept}, params=params,
                         timeout=(10, 45))
    except requests.RequestException as exc:
        raise DataError("Cannot reach the IMF API. Please retry later. " + str(exc)) from exc
    if r.status_code in (204, 404):
        return None
    if not r.ok:
        raise DataError(f"IMF returned HTTP {r.status_code}. Request: {r.url}. "
                        "The service may be unavailable or its API may have changed.")
    return r


@st.cache_data(ttl=86400, show_spinner=False)
def metadata(flow):
    """Resolve the dataflow version and country codes from IMF metadata."""
    r = get_response(f"/structure/dataflow/IMF.STA/{flow}/latest", META_ACCEPT,
                     {"references": "all"})
    if r is None:
        raise DataError(f"IMF {flow} metadata is unavailable.")
    try:
        data = r.json()["data"]
        flows = [f for f in data["dataflows"] if f["id"] == flow]
        if len(flows) != 1:
            raise ValueError("Expected one dataflow")
        version = flows[0]["version"]
        expected = (["COUNTRY", "INDEX_TYPE", "COICOP_1999", "TYPE_OF_TRANSFORMATION", "FREQUENCY"]
                    if flow == "CPI" else ["COUNTRY", "INDICATOR", "TYPE_OF_TRANSFORMATION", "FREQUENCY"])
        structures = data["dataStructures"]
        dimensions = structures[0]["dataStructureComponents"]["dimensionList"]["dimensions"]
        actual = [d["id"] for d in sorted(dimensions, key=lambda d: d["position"])]
        if actual != expected:
            raise ValueError(f"Unexpected {flow} dimensions: {actual}")
        countries = {}
        for cl in data["codelists"]:
            if cl["id"] != "CL_COUNTRY":
                continue
            for code in cl["codes"]:
                key = code["id"]
                if pycountry.countries.get(alpha_3=key) or key == "G163":
                    countries[key] = code.get("names", {}).get("en", code.get("name", key))
        countries["G163"] = "Euro area"
        return version, countries
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        raise DataError(f"Cannot interpret IMF {flow} metadata: {exc}") from exc


def numeric_column(frame, name, default=0):
    if name not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    values = frame[name].fillna("").astype(str).str.split(":").str[0]
    values = values.replace("", str(default))
    result = pd.to_numeric(values, errors="coerce")
    if result.isna().any():
        raise DataError(f"Cannot interpret IMF {name} scaling metadata.")
    return result


def parse_csv(text, flow, country):
    try:
        frame = pd.read_csv(StringIO(text), dtype=str)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise DataError("IMF did not return a readable SDMX CSV file.") from exc
    frame.columns = frame.columns.str.strip().str.upper()
    if "TIME_PERIOD" not in frame or "OBS_VALUE" not in frame:
        raise DataError("Unexpected IMF CSV format: TIME_PERIOD or OBS_VALUE is missing.")
    for col in ("COUNTRY", "REF_AREA"):
        if col in frame:
            frame = frame[frame[col].str.split(":").str[0] == country].copy()
    raw_time = frame["TIME_PERIOD"].str.strip()
    monthly = raw_time.str.match(r"^\d{4}-(?:M)?\d{2}$", na=False)
    frame = frame.loc[monthly].copy()
    time = raw_time.loc[monthly].str.replace("-M", "-", regex=False)
    frame["month"] = pd.to_datetime(time + "-01", errors="coerce")
    if frame["month"].isna().any():
        raise DataError("IMF returned an invalid monthly date.")
    if frame["month"].duplicated().any():
        raise DataError(f"IMF returned multiple {flow} observations per month for {country}. "
                        "A unique series must be selected before calculating RER.")
    value = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
    # SDMX providers may report scaling as UNIT_MULT or SCALE.
    scale_key = "UNIT_MULT" if "UNIT_MULT" in frame else "SCALE"
    value = value * np.power(10.0, numeric_column(frame, scale_key))
    flag_key = "OBS_STATUS" if "OBS_STATUS" in frame else "STATUS"
    flags = frame[flag_key].fillna("") if flag_key in frame else pd.Series("", index=frame.index)
    flag_codes = flags.str.split(":").str[0]
    # Retain estimates/provisional data and their flags, but exclude missing/confidential values.
    unusable = flag_codes.isin(["C", "L", "M"])
    value = value.where(np.isfinite(value) & (value > 0) & ~unusable)
    result = pd.DataFrame({"value": value, "status": flags, "raw_value": frame["OBS_VALUE"]})
    result.index = pd.DatetimeIndex(frame["month"])
    result = result.sort_index()
    return result


@st.cache_data(ttl=21600, show_spinner=False)
def get_series(flow, country):
    version, _ = metadata(flow)
    key = f"{country}.CPI._T.IX.M" if flow == "CPI" else f"{country}.XDC_USD.PA_RT.M"
    r = get_response(f"/data/dataflow/IMF.STA/{flow}/{version}/{key}", CSV_ACCEPT,
                     {"startPeriod": FIRST, "attributes": "dsd", "measures": "all"})
    if r is None:
        return pd.DataFrame(columns=["value", "status", "raw_value"],
                            index=pd.DatetimeIndex([], name="month"))
    parsed = parse_csv(r.text, flow, country)
    return parsed.loc[parsed.index >= pd.Timestamp(FIRST + "-01")]


def calculate(frame):
    """Calculate ONLY on the already-selected, inclusive sample."""
    out = frame.copy()
    for col in ("E1", "E2", "P1", "P2"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].where(np.isfinite(out[col]) & (out[col] > 0))
    out["S"] = out["E2"] / out["E1"]
    out["S"] = out["S"].where(np.isfinite(out["S"]))
    out["RER"] = out["S"] * out["P1"] / out["P2"]
    out["RER"] = out["RER"].where(np.isfinite(out["RER"]) & (out["RER"] > 0))
    out["valid_RER"] = out["RER"].notna()
    benchmark = out.loc[out["valid_RER"], "RER"].mean()
    out["RER_star"] = benchmark
    out["Real_Index"] = 100 * out["RER"] / benchmark
    return out


def month_label(t):
    return t.strftime("%Y-%m")


def main():
    st.set_page_config(page_title="Real Exchange Rate Explorer", page_icon="🌍", layout="wide")
    st.title("Real Exchange Rate Explorer")
    st.caption("FIN 470 · Monthly IMF data · Sample-average benchmark = 100")
    with st.expander("Formula and interpretation"):
        st.latex(r"S_t = E_{2,t}/E_{1,t},\quad RER_t=S_t P_{1,t}/P_{2,t}")
        st.latex(r"RER^*=\operatorname{mean}_{t\in\text{valid selected months}} RER_t,\quad I_t=100RER_t/RER^*")
        st.write("E1 and E2 are local currency units per USD. S is Country 2 currency per "
                 "one unit of Country 1 currency. A rising Real Index indicates real appreciation "
                 "of Country 1 relative to Country 2. An index of 100 is the selected sample average, "
                 "not independently established fair value. CPI index base levels cancel in the normalized index.")
    try:
        with st.spinner("Loading IMF country metadata…"):
            _, countries = metadata("CPI")
            _, er_countries = metadata("ER")
            countries.update(er_countries)
    except DataError as exc:
        st.error(str(exc))
        st.info("Country metadata must load before IMF data can be requested. Try Refresh IMF data below.")
        if st.button("Refresh IMF data"):
            st.cache_data.clear()
            st.rerun()
        st.stop()
    codes = sorted(countries, key=lambda c: countries[c])
    if len(codes) < 3:
        st.error("The IMF response did not include the expected country codelist. "
                 "Check the current IMF structure metadata before proceeding.")
        st.stop()
    left, right = st.columns(2)
    c1 = left.selectbox("Country 1", codes, index=codes.index("USA") if "USA" in codes else 0,
                        format_func=lambda c: f"{countries[c]} ({c})")
    c2 = right.selectbox("Country 2", codes, index=codes.index("GBR") if "GBR" in codes else 1,
                         format_func=lambda c: f"{countries[c]} ({c})")
    months = pd.date_range(FIRST + "-01", pd.Timestamp(date.today()).replace(day=1), freq="MS")
    left, right = st.columns(2)
    start = left.selectbox("Start month", months, index=0, format_func=month_label)
    end = right.selectbox("End month", months, index=len(months)-1, format_func=month_label)
    mode = st.radio("Show", ["Real", "Nominal", "Both"], horizontal=True)
    if st.button("Refresh IMF data"):
        st.cache_data.clear()
        st.rerun()
    if start > end:
        st.error("Start month must be on or before end month.")
        st.stop()
    if c1 == c2:
        st.info("Both selections are the same economy. Valid nominal and real indices will be 1 and 100, respectively.")
    frame = pd.DataFrame(index=pd.date_range(start, end, freq="MS"))
    frame.index.name = "Month"
    warnings = []
    try:
        with st.spinner("Retrieving monthly CPI and exchange rates from the IMF…"):
            for number, country in [(1, c1), (2, c2)]:
                for flow, field in [("CPI", f"P{number}"), ("ER", f"E{number}")]:
                    # USD/USD is an identity, not an imputed missing foreign rate.
                    if country == "USA" and flow == "ER":
                        frame[field] = 1.0
                        frame[field + "_status"] = "USD/USD identity"
                        continue
                    series = get_series(flow, country)
                    frame[field] = series["value"]
                    frame[field + "_status"] = series["status"]
                    frame[field + "_raw_value"] = series["raw_value"]
                    if series.empty or frame[field].notna().sum() == 0:
                        warnings.append(f"No usable {flow} observations for {countries[country]} in the selected sample.")
    except DataError as exc:
        st.error(str(exc))
        st.stop()
    for warning in warnings:
        st.warning(warning)
    result = calculate(frame)
    result.insert(0, "Country_1", countries[c1])
    result.insert(1, "Country_1_code", c1)
    result.insert(2, "Country_2", countries[c2])
    result.insert(3, "Country_2_code", c2)
    units = f"{countries[c2]} currency units per {countries[c1]} currency unit"
    result["S_units"] = units
    valid = result.loc[result["valid_RER"]]
    cols = st.columns(3)
    cols[0].metric("Sample RER*", f"{valid['RER'].mean():.6g}" if len(valid) else "Unavailable")
    cols[1].metric("Valid RER months", f"{len(valid)} / {len(result)}")
    cols[2].metric("RER coverage", f"{month_label(valid.index.min())} to {month_label(valid.index.max())}" if len(valid) else "None")
    nominal_valid = result.loc[result["S"].notna()]
    if len(nominal_valid):
        st.caption(f"Nominal coverage: {month_label(nominal_valid.index.min())} to "
                   f"{month_label(nominal_valid.index.max())}; {len(nominal_valid)} valid months. "
                   "Coverage endpoints may contain gaps between them.")
    if not len(valid):
        st.warning("No overlapping valid CPI and exchange rate observations. Try different countries "
                   "or dates. Available nominal observations can still be viewed and downloaded.")
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    if mode in ("Real", "Both"):
        fig.add_trace(go.Scatter(x=result.index, y=result["Real_Index"], name="Real Index",
                                connectgaps=False, line={"color": "#7456b3"},
                                hovertemplate="%{x|%Y-%m}: %{y:.2f}<extra>Real Index</extra>"), secondary_y=False)
        fig.add_hline(y=100, line_dash="dot", line_color="gray", secondary_y=False)
    if mode in ("Nominal", "Both"):
        fig.add_trace(go.Scatter(x=result.index, y=result["S"], name="Nominal S",
                                connectgaps=False, line={"color": "#16898b"},
                                hovertemplate="%{x|%Y-%m}: %{y:.6g}<extra>Nominal S</extra>"), secondary_y=(mode == "Both"))
    fig.update_yaxes(title_text="Real Index (sample average = 100)" if mode != "Nominal" else units,
                     secondary_y=False)
    fig.update_yaxes(title_text=units if mode == "Both" else None, visible=(mode == "Both"), secondary_y=True)
    fig.update_layout(height=520, hovermode="x unified", xaxis_title="Month",
                      legend={"orientation": "h", "y": 1.12}, margin={"t": 65})
    fig.update_xaxes(rangeslider_visible=True)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Monthly CPI and period-average nominal exchange rates. Missing values remain blank; "
               "no interpolation or historical currency splicing is performed. Euro area coverage "
               "depends on IMF G163 series availability. Currency reforms and statistical breaks "
               "can affect historical comparisons.")
    st.subheader("Observations and calculations")
    display = result.copy()
    display.index = display.index.strftime("%Y-%m")
    st.dataframe(display, use_container_width=True)
    st.download_button("Download selected sample as CSV", display.to_csv(index_label="Month", na_rep="").encode("utf-8-sig"),
                       file_name=f"RER_{c1}_{c2}_{month_label(start)}_{month_label(end)}.csv", mime="text/csv")
    st.caption("Source: IMF CPI and ER datasets, SDMX 3.0 API. Status flags and raw values are "
               "retained in the download. Estimated/provisional numeric observations are retained; "
               "missing, nonpositive, nonfinite and confidential observations are excluded from calculations.")
    st.markdown("[IMF API information](https://data.imf.org/en/Resource-Pages/IMF-API)")


if __name__ == "__main__":
    main()
