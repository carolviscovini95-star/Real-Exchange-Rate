# Real Exchange Rate Explorer

A Python 3.12 / Streamlit application for FIN 470. Select two IMF economies
or the Euro area, dates, and Real, Nominal, or Both. Download every month in
the selected period, including missing observations, as CSV.

## Economic definitions

E1 and E2 are local currency units per USD. The US rate is the identity 1.

* S = E2 / E1: Country 2 currency units per Country 1 currency unit.
* P1 and P2: respective monthly CPI indices.
* RER = S × P1 / P2.
* RER* = arithmetic mean of valid RER observations within the inclusive selected sample.
* Real Index = 100 × RER / RER*.

The benchmark is recalculated when countries or dates change. The nominal
series is never normalized. Both uses separate axes. A rising Real Index
means real appreciation of Country 1 relative to Country 2. The sample mean
is a comparison benchmark, not proof of fair value or misvaluation. CPI base
levels affect raw RER levels but cancel in the normalized index.

## Data

Source: [IMF API](https://data.imf.org/en/Resource-Pages/IMF-API).
Base: `https://api.imf.org/external/sdmx/3.0`.

The app resolves dataflow versions and country codelists through
`/structure/dataflow/IMF.STA/{CPI|ER}/latest?references=all` and requests SDMX CSV
from `/data/dataflow/IMF.STA/{flow}/{version}/{key}`.

* CPI key: `{ISO3}.CPI._T.IX.M`.
* ER key: `{ISO3}.XDC_USD.PA_RT.M` (monthly period average).
* Euro area: `G163`.
* Requested history begins January 1976; actual coverage varies.

Only ISO3 economies present in the IMF metadata and G163 appear in selectors.
Presence in metadata does not guarantee data availability. The app requires
working IMF metadata and supports SDMX CSV with TIME_PERIOD and OBS_VALUE.
If IMF changes its endpoint or schema, the app reports an error.

No values are filled, interpolated, simulated or silently spliced across
currencies. Nonpositive/nonfinite inputs and confidential/missing status
codes C, L and M are excluded. Estimates and provisional numeric observations
remain usable and their flags are retained. UNIT_MULT (or SCALE) metadata is
applied before calculations. Duplicate monthly observations are rejected.
IMF historical currency reforms, CPI breaks, Euro area composition, and
changes of units may limit comparisons. Inspect the downloaded flags and
source metadata before interpreting a long sample. No pre-euro currency is
constructed for G163.

CSV includes E1/E2/P1/P2, available raw values/statuses, nominal S and its units,
raw RER, sample benchmark, Real Index, country identifiers and valid-RER flags.
Every calendar month is retained. Missing numeric values are blank.

## Run locally

Install Python 3.12. In a folder containing all three files:

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

The app needs outbound HTTPS access to api.imf.org. No API key is hardcoded.
Request timeouts and cached metadata/data limit repeat calls. Refresh IMF data
clears the caches. Some networks or IMF service policies may block access.

## Publish

GitHub stores the files; it does not execute the Streamlit Python server.
Upload app.py, requirements.txt and this README.md to the repository root.
On [Streamlit Community Cloud](https://share.streamlit.io/), sign in, create
an app from that GitHub repository, select the main branch and app.py,
select Python 3.12 in deployment settings, and deploy. Check runtime logs
if dependency installation or IMF requests fail. Hosting service interfaces
and policies may change. GitHub Pages alone cannot run this Python app.

## Verification and limitations

The code was syntax checked. Calculation checks passed for exchange rate
quotation, reciprocal rates and raw RER, missing CPI, recalculation after sample
changes, and a mean Real Index of 100. Live IMF metadata and USA/GBR CPI and
GBP/USD exchange rate retrieval succeeded. The January 2000 to December 2020
USA/GBR sample contained 252 valid RER months and its Real Index averaged 100.
Euro area exchange rates loaded from January 1999; the requested G163 CPI
series returned no observations at verification. Such unavailable series are
reported rather than replaced with another indicator.

The Streamlit automated app test completed without exceptions or displayed errors
and rendered the chart controls, data table and metrics.
The hosted deployment remains unverified. A successful country-pair test
cannot establish availability or historical consistency for every economy.

For the first live test, choose United States / United Kingdom and January
2000 through December 2020. Confirm data loads, inspect flags, export CSV,
and verify that valid Real Index values average 100. Change dates and verify
the benchmark changes. Test a country with limited coverage and check that
missing months remain blank. Report any API error exactly as displayed.

Hypothetical arithmetic check: E1=1, E2=5, P1=120, P2=150 gives S=5, RER=4.
These are test inputs only and never appear in the live application.
