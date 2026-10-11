# Foresight: specification audit and implementation plan

Historical pre-implementation audit. The approved work has now been implemented; see [current acceptance evidence](implementation-acceptance.md). Findings below describe the earlier state and are retained for traceability.

Audit date: 10 October 2026. Scope: desktop only, per user instruction.
No application fixes made during this audit.

Source specification: supplied “Foresight — Consolidated Implementation Prompt”.
Visual references found and inspected in `Resource`: `Foresight Bitcoin dataset explorer.png` (1672×941) and `Price & Volume forecast inspection.png` (1536×1024). Compared the running desktop UI at those viewport sizes. No standalone unobstructed Main Dashboard reference is present; the Inspect reference shows part of that dashboard. Theme is broadly aligned, but geometry, typography and chart presentation are not.

## Verdict

Not aligned with the complete specification. A functioning dataset explorer exists. Forecast Lab is an illustrative frontend, not a forecasting system. Larger charts and improved layout do not establish functional completeness.

## Requirement coverage

| Specification | Current evidence | Status |
|---|---|---|
| 1. Existing app/reference | Explorer and Inspect references found; measured desktop layout differs; standalone dashboard reference absent | Partial / visual mismatch |
| 2. Scope | BTC/ETH explorer; Forecast Lab mockup; no forecasting services | Partial |
| 3. Stack/separation | Python, FastAPI, React/TS/Vite, Parquet, shared data CLI; no SQLite/model storage; frontend dependency ranges rather than exact pins | Partial |
| 4. End-to-end | Import → parse → validate → explorer works; training through promotion absent | Missing after dataset stage |
| 5. Dataset | Archives/checksums, bounded downloads, retry, UTC normalization, fields and reports exist; integrity and cancellation gaps remain | Partial |
| 6. Periods | Correct half-open intervals and 36/8/4 month durations; no forecasting examples or leakage controls | Partial |
| 7. Forecast definition | Hardcoded chart and weekly values; no precise target convention, calibrated intervals or probability model | Missing |
| 8. Specialist | No features, numerical model, chronological selection, calibration or artifacts | Missing |
| 9. Contract | Only dataset/import schemas; no versioned forecast/provenance validation | Missing |
| 10. Coordinator | Static card and weight; no validated distinct pass-through output | Missing |
| 11. Publisher | Static saved status; no immutable forecasts, idempotency or history | Missing |
| 12. Evaluator | Static MAE/coverage/baseline values; no scoring/baseline services | Missing |
| 13. Replay/retraining | Slider changes UI state; Play only toggles state; no replay clock, modes, maturity gates, promotion or rollback | Missing |
| 14. Dashboard | Four cards/chart/summary present; primary actions have no handlers; labels differ from Train & Backtest / Predict Next 7 Days | Mockup |
| 15. Inspect | Drawer opens; contents illustrative; missing real provenance, seven forecast rows, quality and scoring records | Mockup |
| 16. Chart/summary | Static SVG; no forecast pan/zoom, crosshair tooltips, point selection or history binding | Mockup |
| 17. Evaluation/history UI | Navigation disabled; frozen/adaptive selection, sample counts and real replay controls absent | Missing |
| 18. Explorer UI | Real candles, split filtering, inspector, export, import dialog; misleading quality strings, rounded percentages, mostly display-only interval/date/timezone fields | Partial |
| 19. States | Preview labels exist; agent statuses hardcoded; missing model/job/error/partial-evaluation state flows | Partial |
| 20. APIs/jobs | Only dataset/import APIs; jobs in memory, no persisted recovery | Partial |
| 21. Acceptance | 16 dataset tests pass; no forecast/replay acceptance suite, model artifacts, saved forecasts or evaluation reports | Partial |

## Confirmed defects and limitations

### Data correctness and truthful state

- `DatasetDetails.tsx:28,200–214`: UI overrides warning state and hardcodes “Verified (35,063 rows)”, zero errors and one missing hour. Actual BTC report says `status=warnings`, `is_verified=false`.
- `validator.py`: non-negative volume check accepts positive infinity. An in-memory probe with infinite quote volume reported zero invalid-volume rows.
- Duplicate conflict detection compares OHLC only. An in-memory probe with differing base volume at identical timestamps reported zero conflicting duplicates.
- Downloader may retain/download unverified archives when a published checksum is unavailable. Processor reads raw ZIP files independently of manifest verification.
- Processor catches archive parsing failures and continues; import can reach Complete with partial records. Readiness must distinguish complete, warning and failed/incomplete imports.
- Processed Parquet, report and manifest writes are not all atomic or committed as one consistent dataset version.
- Job registry is memory-only. Pending is excluded from active-job detection; processing cancellation lacks a cooperative token throughout parsing/validation/saving. Processing progress updates descriptive text without consistently updating job status.
- Dataset dates are constants, but month generation, expected counts and UI coverage strings are independently hardcoded. One configuration must drive all of them.
- Missing candles are preserved in storage, but chart series omit missing hourly slots; explicit time-gap visualization remains necessary.

### Forecast/UI correctness

- `ForecastLabView.tsx:187–225`: both primary action buttons lack workflow handlers.
- Agent statuses and model versions are static; preview labels correctly acknowledge illustrative content but do not make the statuses real.
- Forecast chart is an SVG drawing. No stored data, target timestamps, forecast selection, calibrated uncertainty or tooltip data.
- UI shows origin 1 June and day-seven endpoint 8 June, but prices/bounds are independently hardcoded across chart, summary and drawer. Their agreement is not enforced by a shared forecast record.
- Replay Play changes a boolean only; stepping changes displayed dates without loading saved forecasts or enforcing outcome availability.
- Inspect tabs mostly change styling; no separate real input/output/evaluation datasets.
- The prohibited stages panel is absent. A “Train → Validate → Forecast → Evaluate” text line remains; remove/approve that against the selected reference rather than introducing a stepper.
- No proof of model performance. Illustrated 58% probability, 76% coverage and -18% baseline comparison are not measured results.

## Ordered implementation plan — requires approval before implementation

### 1. Lock design and forecasting conventions

Use the supplied Resource Explorer and Inspect references at their native desktop dimensions. Confirm the unobstructed dashboard composition where the Inspect reference hides it. Confirm one target-price convention, daily UTC cadence, zero-return treatment, look-back candidates, development subdivisions, frozen/adaptive settings, and predeclared promotion policy. Preserve BTC-only forecasting and ETH explorer access. Treat consolidated functional requirements as authoritative when reference examples contain incorrect dates, durations or obsolete navigation labels.

Exit: approved requirements/reference matrix; no unresolved scientific conventions.

### 2. Harden existing data and jobs

Make metadata/quality text dynamic. Complete finite-value and duplicate checks. Require manifest-backed integrity; preserve gaps. Make dataset publication atomic/versioned. Implement durable SQLite jobs, conflict prevention, restart recovery and cancellation. Centralize date/count configuration and expose readiness/errors.

Exit: real BTC import/inspection/export; failure, warning, cancellation and restart tests pass.

### 3. Build causal training and model lifecycle

Create shared services/CLI for completed-candle availability, causal features and horizon-specific eligible examples. Train manageable candidate families using permitted periods only. Select settings and calibrate pointwise intervals on earlier development data. Save models, dataset/config IDs and provenance. Implement evidence-based promotion and rollback.

Exit: saved selected model; target-boundary, future-input, preprocessing and calibration tests pass. Final test remains unused for selection.

### 4. Add contracts, coordination and publishing

Define versioned seven-point forecast contracts with probabilities, interval definitions and provenance. Validate horizon/availability/finite values. Coordinator creates a distinct linked output with weight 1.0 and unchanged predictions. Publisher commits immutable specialist/coordinated records before display. Implement idempotent retries/history.

Exit: contract rejection, pass-through equality, immutable persistence, idempotency and restart tests pass.

### 5. Implement evaluator and both replay modes

Use exact target candles and simulated availability. Score each horizon and weekly probabilities; compute documented earlier-data baselines and sample counts. Separate frozen/adaptive runs. Implement retraining on matured targets only, incumbent/candidate comparison, recorded decisions and rollback. Handle pending/missing outcomes without substitution.

Exit: hand-calculated metric tests; maturity/missing-data tests; full historical replay report including baseline failures and overlapping-window uncertainty handling.

### 6. Wire desktop dashboard and Inspect

First establish reusable desktop shell dimensions, readable typography and panel spacing from the references. Give the Explorer separate price/volume regions and a readable bottom inspector. Make Inspect a full-height right overlay with its own scroll region. Replace the stretched forecast SVG with an interactive chart whose axes and text retain their proportions; implement the detailed Inspect mini-chart. Then replace static values/statuses with selected persisted run/model/forecast state. Implement Train & Backtest and Predict Next 7 Days as separate workflows. Add configuration, progress/cancel/error states. Bind chart/summary/Inspect to one forecast record. Add chart interaction, saved-history selection, replay run/origin/speed navigation, Evaluation and Forecast History views. Keep preview labels until real data exists.

Exit: complete desktop workflow, synchronized dates/values, honest states, no unrelated jobs shown as one pipeline.

### 7. Acceptance and handoff

Run complete import → train → frozen/adaptive replay → predict → inspect → evaluate → rollback workflow. Compare desktop screenshots with the approved references at the same viewport, checking geometry separately from changing data pixels. Deliver exact dependencies, shared CLI, setup notes, artifacts, example forecasts, replay reports and known limits.

Exit: all specification acceptance checks supported by evidence. Profitability/predictive superiority is not assumed or required; reported results must be truthful.

## Desktop reference comparison

Dimensions below describe this audit's measured render, not proposed fixed widths for every desktop.

| Area | Reference | Current UI / required work |
|---|---|---|
| Explorer shell at 1672×941 | Header about 54px; sidebar about 139px with horizontal icon/text navigation; details about 287px | Header 35px; sidebar 88px; details 216px. Restore reference proportions and readable control sizing. Keep specification-required navigation. |
| Explorer composition | Three split cards sized approximately 56% / 22% / 22%; clearly separated price and volume areas; bottom inspector extends beneath the navigation area | Current layout has different card/panel proportions and a compact inspector inside the center column. Rework desktop grid and vertical allocation against reference. |
| Explorer typography | Reference table/details visibly readable at native size | Details use 9.5px text; multiple controls are similarly small. Adopt a consistent readable desktop type scale. |
| Inspect at 1536×1024 | Right overlay starts at top of viewport; approximately 582px wide; independent scrolling | Embedded beside chart at x1158, y174.5, width360, height813.5. Change panel placement, width and scroll behavior. |
| Inspect content | Large title, clear evidence/forecast/evaluation sections; mini-chart has axes, grid, dates, point markers and legend | Title 11px; subtitle 8.5px; compact sparkline lacks the reference chart detail. Restore hierarchy and chart information. |
| Forecast chart | Balanced plot with readable labels; replay/evaluation panels remain proportionate | Current SVG stretches to the available height using `preserveAspectRatio="none"`, distorting labels and geometry. Use chart layout that resizes plot area without stretching text. |

The earlier small-test-graph issue was improved by the prior layout work, but enlarging a canvas alone does not establish reference fidelity or readable data density. Final acceptance must include full-history and test-only views at both reference desktop sizes, with and without Inspect open.

Reference sample facts must not be copied literally: the Explorer training-duration example and Inspect date examples contain inconsistencies. Preserve the consolidated specification's 36/8/4-month splits and exact +24…+168-hour targets.

## Validation performed

- Read current backend, frontend, CLI, tests, reports and supplied specification.
- Inspected running desktop dashboard and specialist drawer at 1440×900.
- Inspected both Resource PNGs and compared the live Explorer at 1672×941 and Inspect at 1536×1024; measured DOM panel bounds and font sizes. Restored browser viewport override afterward.
- Confirmed primary action has no operational effect; source also lacks its handler.
- Live OpenAPI lists only dataset/import/health routes.
- Dataset suite: 16 passed, one Starlette/httpx deprecation warning.
- Frontend TypeScript no-emit check and lint passed.
- Infinite-volume and volume-only duplicate-conflict probes confirm validation gaps.
- No downloads, training jobs or application fixes performed.

Mobile is excluded from the proposed acceptance scope by the user's latest instruction.
