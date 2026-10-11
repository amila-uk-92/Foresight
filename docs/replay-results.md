# Foresight replay results (final test, June–September 2026)

Measured 10 October 2026. The frozen and adaptive replays were re-run with the CLI after the gap-closure changes (`train-backtest --mode frozen`, then `--mode adaptive`, default candidates). They reproduced the earlier saved runs to the cent. Both runs are labelled **Final test** / **Adaptive final-test replay**, not development: the configuration matches the protocol first reported, and the model code is unchanged.

## Setup

- Data: BTCUSDT 1h, Binance Spot, 35,063 of 35,064 hours (one real gap, 2023-03-24 13:00 UTC). Dataset version `50e0fd47…1c6`.
- Selected model: direct ridge regression on log returns, 30-day look-back, penalty α = 100. These won selection on Oct 2025–Jan 2026 data out of 9 candidates (30/90/180 days × α 1/10/100), with selection MAE 3,464 USDT. Calibration used Feb–May 2026.
- Origins: 122 daily origins at 00:00 UTC, 1 Jun to 30 Sep 2026. No origin was skipped.
- Baselines (estimated at each origin from earlier data only): no-change median, historical-frequency rise probability, and empirical 10th/90th percentile log-return intervals.

## Accuracy by horizon (coordinated output; specialist output identical)

| Horizon | n | Model MAE (USDT) | No-change MAE | MAE 95% block-bootstrap | Model 80% coverage | Baseline coverage | Model interval score | Baseline interval score |
|---|---|---|---|---|---|---|---|---|
| +24h | 122 | 1,026 | 1,011 | 817–1,272 | 86.1% | 76.2% | 5,678 | 6,195 |
| +48h | 121 | 1,594 | 1,568 | 1,204–2,027 | 84.3% | 70.2% | 8,475 | 9,358 |
| +72h | 120 | 1,896 | 1,907 | 1,365–2,520 | 84.2% | 71.7% | 10,848 | 12,216 |
| +96h | 119 | 2,226 | 2,190 | 1,499–2,952 | 85.7% | 65.5% | 12,770 | 15,120 |
| +120h | 118 | 2,569 | 2,476 | 1,701–3,421 | 83.9% | 65.3% | 14,576 | 18,274 |
| +144h | 117 | 2,818 | 2,817 | 1,853–3,841 | 80.3% | 66.7% | 15,376 | 20,324 |
| +168h | 116 | 3,086 | 3,056 | 2,000–4,362 | 77.6% | 65.5% | 16,493 | 22,148 |

Targets: 833 scored, 21 pending (the last six origins' horizons run past the end of the data), 0 unscorable.

## Day-seven direction

| Metric | Model | Baseline |
|---|---|---|
| Direction accuracy | 50.0% (n = 116) | — |
| Brier score, P(rise) | 0.255 | 0.319 (historical frequency) |

Calibration bins: 106 forecasts had P(rise) 40–60% (mean predicted 50.6%, observed 55.7%). 10 had 60–80% (mean predicted 63.7%, observed 40.0%). No other bin had samples.

## Adaptive retraining

Candidates were trained every 30 days, on 1 Jul, 31 Jul, 30 Aug and 29 Sep. Each was compared with the incumbent and the baselines on the same 39 earlier matured daily origins. **All four were rejected**, so adaptive results equal frozen results.

| Clock | Candidate MAE | Incumbent MAE | No-change MAE | Outcome |
|---|---|---|---|---|
| 1 Jul | 3,195 | 3,245 | 3,255 | Retained incumbent: failed interval-score or coverage gate |
| 31 Jul | 2,423 | 2,260 | 2,315 | Retained: worse MAE |
| 30 Aug | 1,614 | 1,517 | 1,508 | Retained: worse MAE |
| 29 Sep | 3,165 | 2,766 | 2,642 | Retained: worse MAE |

Every adaptive decision records `uses_final_test_outcomes: true`. It used final-test outcomes that had matured by the simulated clock, as the adaptive protocol allows.

## Interpretation

- **Median accuracy:** the model does **not** beat the no-change forecast. Its MAE is within ±4% of no-change at every horizon and slightly worse at 5 of 7. The bootstrap intervals overlap heavily.
- **Intervals:** the model's 80% intervals are better calibrated than the baseline's. Coverage is 78–86% against 65–76%, and the interval score is better at every horizon. Short horizons over-cover slightly; day 7 under-covers slightly.
- **Direction:** day-seven direction calls are no better than a coin flip. The probability is better than the historical-frequency baseline mainly because it stays near 50%.
- **Selection:** the strongest penalty and the shortest look-back won selection, both at the edge of the grid. That points to features carrying little usable signal at these horizons.

These results were not used to tune the model. Any change made in response to them will make later runs show as development.
