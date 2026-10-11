# Foresight implementation acceptance

10 October 2026. Implements the approved seven-part plan in `spec-validation-plan.md`. The gap-closure update below extends acceptance to mobile layouts. The earlier audit is historical; no mock UI or synthetic production fallback remains.

## Completed plan

| Plan | Implementation / evidence |
|---|---|
| 1. Conventions and design | UTC completed-candle targets; seven daily horizons; empirical exact-zero probability; 30/90/180-day lookbacks; separate chronological selection/calibration; frozen/adaptive protocols and fixed promotion gates documented in README. Resource Explorer and Inspect references inspected at 1672×941 and 1536×1024. |
| 2. Data/jobs | Mandatory archive checksums and manifest-backed parsing; finite volume/trade and full duplicate-conflict validation; preserved missing hours; atomic dataset bundles/current pointers; durable reservations, cooperative cancellation and restart recovery. Real UI import completed using 48 verified BTC archives. |
| 3. Model lifecycle | Genuine causal features, fitting-only standardization, direct ridge numerical models, earlier-data selection/residual calibration, immutable snapshot/model provenance. Models saved on disk and SQLite. Leakage, split boundary and future-mutation tests pass. |
| 4. Contract/coordinator/publisher | Validated seven-point contract, linked distinct coordinator output, unchanged prediction pass-through and weight 1.0. Publisher rejects changed output; atomic idempotent immutable pair publication and persistence tested. |
| 5. Evaluation/replay | Exact maturity and missing-target handling; horizon metrics, earlier baselines, probabilities and block-bootstrap uncertainty. Complete frozen/adaptive daily replays; controlled candidate comparison, retained decisions and rollback. |
| 6. Desktop UI | Real training/predict/evaluate controls, progress/cancel/error states, model selection, real history/run navigation, working playback and clock, model/component evaluation filters and exports. Separate price/volume panes; larger test graph; readable bottom inspector spanning below navigation and chart; full-height 582px Inspect overlay with independent scrolling, provenance, actual paginated inputs, forecast/evaluation tabs and mini-chart. Interactive chart axes/text are not stretched. |
| 7. Acceptance/handoff | Actual artifacts, replay reports, screenshots, shared-service CLI, pinned dependencies and rewritten setup/protocol documentation. 40 tests pass; frontend build and lint pass. |

## Real artifacts and outcomes

- BTC: 35,063 of 35,064 expected hourly candles. Missing `2023-03-24 13:00 UTC`; status remains warnings, not falsely verified. No missing candle was invented.
- Atomic import bundle: `data/bundles/BTCUSDT/f205fb1fd5304f7bb0e0b88879630fce/`.
- Forecast dataset version: `50e0fd479bb810c38f0ccc38dbc7ae7bbf519ca7a1b700a88e557461204c1dc6`.
- Frozen UI run: `e2267f9ed48b40508233e9d3e55ad3e3`, model `pv-3aed3752e467`, 122 daily origins, zero skipped final-test origins.
- Adaptive run: `2fc53334a9554ddba91f9feda3f43dfa`, 122 daily origins, zero skipped final-test origins. Four candidate comparisons, 39 eligible daily origins each; all retained incumbent because promotion gates failed.
- UI cancellation: run `2782f98b875f4071b8d8d7a5aa7e422a` interrupted; already published immutable records retained. Restart preserves models, runs and predictions.
- UI historical prediction: `986201e4-396b-52ef-8768-a39ec7519900`, origin 1 June 2026, day-seven target 8 June, median 73,679.30 USDT. Explicit 8 June outcome clock evaluates all seven targets. This bad week reports 9,404.92 USDT average horizon error and 0% coverage; values are measured, not decorative.
- Latest-dataset prediction: `8a95a4df-caf4-5c6e-a0b0-45175ca2d908`, origin 1 October 2026. Seven future targets remain pending; repeating the same prediction does not create duplicates.
- Inputs: a 30-day window uses 720 hours plus one boundary close, 721 actual hourly candles. Pagination verified. New contracts record this exact count; existing immutable contracts remain unchanged, while UI correctly explains the boundary input.
- UI rollback switched to `pv-7c5d8852873c` and back to `pv-3aed3752e467`, recording both decisions without changing saved predictions.
- Manual UI retraining at 30 September produced `pv-b2c00a87e5c9`; comparison had 39 origins, coverage 64.8% and worse interval score. Incumbent retained.
- Replay speed/play advanced stored origins from 2 to 19 June; each displayed clock advanced with origin and evaluation stayed 0/7 matured. Playback did not train.
- History selection reopened the stored 1 June prediction. Forecast and evaluation JSON download controls returned real files. No browser console errors in the final inspection.

Replay reports: [frozen](../data/reports/frozen-replay-evaluation.json), [adaptive](../data/reports/adaptive-replay-evaluation.json). Example forecast: [JSON](../data/reports/example-forecast.json). Full source data, model artifacts and durable records remain under `data/`.

## Measured performance

Frozen and adaptive prediction metrics agree because every adaptive candidate was retained. Day-seven sample count: 116; MAE: **3,086.15 USDT**; no-change MAE: **3,056.01 USDT**; 80% interval coverage: **77.59%**. The model has not demonstrated better price accuracy than no-change. Overlapping daily windows mean outcomes are dependent; reported seven-day block-bootstrap intervals are descriptive. These results were not used to tune the final-test model.

## Desktop evidence

Screenshots show actual local state and real records. Geometry/typography were inspected separately from changing data pixels. This is functional/reference-aligned desktop implementation, not a claim of pixel-identical reproduction: no unobstructed standalone dashboard reference was supplied, and reference sample dates/counts were corrected to actual data and the specification.

- [Explorer 1672×941](../screenshots/implementation/dataset-desktop.png)
- [Test graph 1672×941](../screenshots/implementation/test-desktop.png)
- [Explorer 1536×1024](../screenshots/implementation/dataset-desktop-1536.png)
- [Test graph 1536×1024](../screenshots/implementation/test-desktop-1536.png)
- [Forecast dashboard 1536×1024](../screenshots/implementation/forecast-desktop.png)
- [Inspect 1536×1024](../screenshots/implementation/inspect-desktop.png)
- [Evaluation 1536×1024](../screenshots/implementation/evaluation-desktop.png)

## Verification

`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider tests -q`: **55 passed** (after the gap-closure update), one upstream Starlette/httpx TestClient deprecation warning. `npm run build`: pass. `npm run lint`: pass.

Meaningful tests cover exact completed candles, seven targets, future-feature mutation, final-test mutation, fitting scaler boundaries, calibration boundaries, gap exclusions, invalid contracts, pass-through equality, immutable/idempotent publication, restart, missing/maturing targets, hand-computed metrics, job conflict/cancellation/recovery, candidate maturity/comparison separation, promotion gates, rollback, finite volume/trades and duplicate conflicts, checksum rejection and atomic publication, plus real HTTP prediction/input/evaluation workflows.

Local service is bound to 127.0.0.1:8000, serving the built frontend and API. Mobile, live market streaming, trading execution, news and additional specialist families are excluded. Predictive superiority is not an implementation acceptance condition.


## Gap-closure update (10 October 2026, evening)

These changes close the gaps found by comparing the code against the Consolidated Implementation Prompt.

| Spec § | Gap | Change |
|---|---|---|
| 6, 13 | The development label only noticed changes to look-backs, alphas, feature names and periods | The protocol fingerprint now also covers the promotion policy and the source of the feature, selection, calibration, training and prediction functions. Existing stored protocols migrate without relabelling when their configuration matches. Models with a training cutoff inside the final test flag every forecast. Promotion decisions record `uses_final_test_outcomes`. Adaptive runs are labelled separately from frozen. |
| 15, 20 | Agent cards were partly inferred in the UI; Rejected, Failed and Unscorable never appeared | New `agent_status` service and the `/forecasts/{id}/agents`, `/runs/{id}/agents` and `/agents` endpoints. Replay failures are attributed to the specialist, coordinator or publisher (`skipped_origins[].agent`). Unrelated running jobs no longer drive a forecast's cards. The Evaluator follows the replay clock and can show Unscorable. |
| 17 | Forecast History lacked run, weekly estimate and evaluation status; Evaluation lacked counts, per-model horizons and a frozen/adaptive comparison | A paged `/forecasts` history API and table with run, mode, day-7 median, implied return, interval, P(rise), evaluation state and filters. Evaluation adds scored/pending/unscorable counts, forecast-state counts, an MAE table by model version and horizon, and a "Compare with" run selector that shows frozen and adaptive side by side. |
| 16 | Fixed 30-day chart history | A history range selector: 7, 30, 90, 180 or 365 days before the origin. Changing it keeps the selected forecast, point and replay clock. |
| 18 | Gaps only implicit on the explorer chart | Missing hours are marked "Nh missing" and counted under the chart. The volume axis is labelled as USDT quote volume. |
| 19 | Desktop only; generic error on backend loss; selections lost on reload | Single-column phone layout and stacked tablet layout with no horizontal page overflow at 390px. An explicit "backend unavailable, retrying" state. Forecast, run and history range are remembered across reloads. |
| 20 | Models, runs and history only through `/state`; no forecasting job lookup | Added `/models`, `/models/{id}`, `/runs`, `/runs/{id}`, `/runs/{id}/origins` and `/jobs/{id}`. `/state` no longer returns every run's full summary. |
| 3 | The CLI duplicated evaluation logic and couldn't set candidates | `Engine.evaluate_at` and `Engine.history` are shared by the API and CLI. `train-backtest --lookbacks/--alphas`, plus new `runs` and `agents` commands. |
| 8 | Feature formulas were not saved with models | `FEATURE_DEFINITIONS` is stored in every new model artifact. |
| 5 | The dataset pointer stored an absolute Mac path | The pointer is now relative to `data/`, and legacy absolute pointers are still resolved. |
| 21 | No chart/summary agreement test; replay results not written up | 15 new tests in `tests/test_forecast_lifecycle.py`, with shared fixtures in `tests/conftest.py`. [Replay results](replay-results.md) records the measured outcome, including that the model doesn't beat no-change on MAE. |

Still open: no Main Dashboard reference image has been supplied, so the dashboard can't be compared against the selected design.

Screenshots from this update are in `screenshots/gap-closure/`, at 1672×941, 1536×1024 and 390×844.
