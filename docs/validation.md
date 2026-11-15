# Validation

Hand checks and comparisons with NASA's own tools (steps 2 and 9). Owner: D; B writes the stats notes.

SI-assisted: parts of this file were drafted with Claude (Anthropic) and reviewed by the team

## Stats engine calibration (B, step 2)

How often does `analyze()` get it right on synthetic series where we know the truth? 200 series per row,
45 years of monthly data, seasonal cycle plus noise; "flat" = no trend, "trend" = +0.3 °C per decade.
`phi` is the month-to-month autocorrelation of the noise (real monthly anomalies are autocorrelated).
Run on 14 Nov 2026 with `td/sample.py` (synthetic, test-only data).

| Noise | False "significant" on flat series (ideal: 5% or less) | 95% interval contains the true slope (ideal: 95%) | Mann-Kendall fallback used |
| --- | --- | --- | --- |
| White (phi = 0) | 7.0% | 94.5% | 2 of 400 |
| phi = 0.5 | 8.0% | 92.5% | 1 of 400 |
| phi = 0.8 | 11.5% | 87.5% | 4 of 400 |

What this means:

- With white or moderately autocorrelated noise the method is close to its nominal level, but slightly
  overconfident: the "95%" interval covers the truth about 92 to 95% of the time, and flat series are called
  significant 7 to 8% of the time instead of 5%.
- With strong autocorrelation (phi = 0.8) it is clearly overconfident (87.5% coverage, 11.5% false alarms).
  Newey-West errors with 12 lags do not fully correct for it. Report our intervals as "approximately 95%".
- 200 series per row means each rate is uncertain by about ±2 percentage points.
- Possible improvement (not done yet, needs a decision): widen the interval with the lag-1
  autocorrelation of the residuals (effective sample size, as in Santer et al. 2000).

**Mann-Kendall NaN bug (fixed).** The Hamed-Rao variance correction can turn negative, giving p = NaN (7 of
1,200 series above, all with a strong apparent trend). A NaN made `p_mk < 0.10` false, so the tier was
silently decided by the t-test alone and the verdict printed "p = nan". `analyze()` now falls back to the
pre-whitening Mann-Kendall test, sets `mk_fallback = True` and says so in the verdict. The fallback was
chosen by testing: on flat phi = 0.8 series where Hamed-Rao failed, the original, Yue-Wang and trend-free
pre-whitening tests all returned p = 0.0000 (false alarms); pre-whitening returned 0.16, 0.04 and 0.16.

**Minimum record.** `analyze()` needs at least 60 months (was 24): each calendar-month mean needs several
years for the anomalies to be meaningful.

## Hand check on real data (B, step 2)

To do once `fetch_box()` is merged: annual means of Tunisia temperature in a spreadsheet, straight-line
trend per decade, compared with the app's OLS slope.
