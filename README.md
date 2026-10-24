# Real-Exchange-Rate
App and economic requirements:
• Allow users to choose Country 1 and Country 2 from IMF countries and the Euro area. Retrieve monthly IMF CPI and exchange-rate data from January 1976 where available.
• Define S(t) as units of Country 2 currency per one unit of Country 1 currency; let P1(t) and P2(t) be the respective monthly CPIs. Calculate RER(t) = S(t) × P1(t) / P2(t).
• Over the user-selected start and end months, calculate RER* = average of RER(t) over valid months; plot Real Index(t) = 100 × RER(t) / RER*. Recalculate RER* if dates change. Plot nominal S(t) in actual currency units—do not normalize it.
• Let users select Real, Nominal, or Both in interactive charts (use separate axes for Both) and provide a CSV download button of all observations and calculations within the selected sample period.
Data hints: IMF API fetch is https://api.imf.org/external/sdmx/3.0; monthly CPI key {ISO3}.CPI._T.IX.M ; exchange-rate key {ISO3}.XDC_USD.PA_RT.M, where ISO3 is the country code. The IMF uses G163 for the Euro area. IMF exchange rates are local-currency units per USD, so convert them to the stated S(t) direction. Ask your LLM for complete three files: app.py, requirements.txt, and README.md files compatible with Python 3.12. IMF data may have gaps or limited coverage.
