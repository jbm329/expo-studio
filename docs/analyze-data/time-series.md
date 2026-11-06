# Time Series

Use **Time Series** to prepare one numeric value series indexed by a
datetime column. Choose the columns and optional processing settings, then
select **Apply**.

## Prepare one series {#prepare}

1. Select a native **Datetime** column and a numeric **Value** column.
2. Leave **Resampling** set to the original frequency, or choose daily,
   weekly, monthly, quarterly or yearly resampling.
3. Keep **Auto-detect period** selected when the detected frequency has a
   supported default, or clear it and enter a **Seasonal period**.
4. Choose **Additive** or **Multiplicative** decomposition.
5. Select **Apply**.

Duplicate timestamps are averaged. Invalid dates, missing values and
non-finite values are excluded and counted. Resampling averages values in
each interval; missing intervals remain gaps and are not interpolated.
At least three observations must remain.

## Autocorrelation and seasonal decomposition {#diagnostics}

Autocorrelation is available only for a regular series without gaps. The
application reports up to 40 nonzero autocorrelation lags, further limited
to half the number of observations. This lag limit does not truncate the
series.

Seasonal decomposition also requires a regular series without gaps and at
least two complete seasonal cycles. The period is the number of
observations in one cycle. When a frequency has a built-in period, automatic
detection uses 24 for hourly, 7 for daily/business-day, 52 for weekly, 12
for monthly and 4 for quarterly data. If a period is not detected, choose
one manually.

The period control accepts values from 2 to 10,000. Multiplicative
decomposition requires every value to be greater than zero; choose
additive decomposition if the series contains zero or negative values.
Unavailable diagnostics and decomposition are explained in the result rather
than filled by interpolating gaps.

## Export {#export}

After a successful analysis, select **Export** for available series,
autocorrelation, decomposition and chart outputs. For shared export steps and
report workflows, see [Export data](../export-and-report/index.md).
