# Foresight — Multi-Specialist Reasoning and Forecasting Specification v2

Revision: 11 October 2026. Status: updated target design and implementation plan; these new capabilities are not claims about the running app. Documentation changes only are authorized by this revision. Future implementation is staged according to [the revised plan](multi-agent-implementation-plan.md).

Build Foresight as an evidence-grounded, multi-specialist AI reasoning system for Bitcoin seven-day forecasts, with a later paper-trading extension. Preserve the working market-data, numerical forecasting, immutable publishing and evaluation foundation. Add language-model reasoning where it can extract new information, challenge evidence or propose testable improvements. Numerical models compute prices, uncertainty and calibrated probabilities; deterministic code enforces data availability, contracts, risk limits and promotion decisions.

The objective is lower errors and well-calibrated uncertainty on unseen outcomes. More agents, persuasive explanations and agreement between agents do not establish predictive confidence or profitability. Each reasoning component must justify its inclusion through controlled comparisons. No accuracy increase is promised in advance.

This document revises the original specification and incorporates the later desktop-only and unified tabbed-workspace decisions. The original is preserved in [the v1 archive](foresight-specification-v1-archived.md). Where the old audit or implementation reports differ, they remain historical evidence; this document describes the new target, not completed implementation.

## 1. Existing application and design references

The historical dataset explorer has been reported complete. Inspect the existing repository and verify its functionality before extending it.

Reuse working data services, storage, API contracts and approved design tokens. Correct missing requirements where necessary.

Reference inputs already available in the project:

- `Resource/Foresight Bitcoin dataset explorer.png`.
- `Resource/Price & Volume forecast inspection.png`.
- Later agreed desktop layout: one large tabbed forecast/testing workspace, primary prediction blue, actual price white, and model toggles inside graphs.

A separate unobstructed Main Dashboard reference has not been supplied. Use the latest written layout decision and existing tokens; do not mix unrelated dashboard alternatives or claim an absent reference was matched.

Treat the supplied reference as the visual specification. Match its layout, typography, colours, spacing, borders, icons and component proportions.

Approved factual corrections take precedence over illustrative content:

- Training duration is 36 months.
- Prices, counts, probabilities and metrics must come from actual data and model outputs.
- Statuses must reflect real processing states.
- Forecast dates must agree across the chart and summary.
- A median forecast must be labelled “Median,” not “Expected.”
- Concept and illustrative labels are removed only when genuine outputs are displayed.
- Baseline labels must describe the actual baseline being evaluated.

Do not embed a screenshot as the application. Implement the components and their interactions.

## 2. Scope and phased specialist activation

Primary scope remains Bitcoin spot, seven daily horizons, local research and truthful evaluation. Preserve the existing market registry and any Ethereum explorer data. Add other markets only through explicit market-specific configuration.

Design the complete hierarchy now, activate it incrementally:

1. **Numerical foundation:** Price & Volume specialist, deterministic technical features, candidate model families, coordinator, publisher, evaluator and controlled model lifecycle.
2. **First reasoning specialist:** News & Macro agent extracts sourced structured events; a separately trained numerical news forecaster converts those events into seven-day distributions. An augmented price-plus-news model is also an experimental comparator.
3. **Research team:** independent initial Bull and Bear evidence reviews, bounded rebuttal and a moderator; an Experiment agent proposes feature/model changes for offline evaluation.
4. **Multi-specialist coordination:** development-trained ensemble weights, chronological uncertainty recalibration and missing-specialist fallback.
5. **Reflection:** versioned hypotheses and prompt candidates based on matured earlier outcomes, with controlled evaluation and rollback.
6. **Optional specialists:** on-chain fundamentals, derivatives/liquidity, social sentiment and multimodal inputs, added individually after data and usefulness checks.
7. **Paper trading:** strategy synthesis, contrasting risk reviews, hard quantitative constraints and an orchestration/fund-manager layer. Real orders remain outside this revision.

Ten numerical families are candidate estimators within a specialist, not ten independently informed specialist agents. Families and active subsets are explicit configuration; do not silently change their membership. Multiple agents using the same evidence do not count as independent confirmation.

No account credentials, live trading, short selling, leverage or production deployment are enabled by this design update. No data subscription or external AI service is selected or purchased here. A later live-execution proposal needs a separate reviewed scope.

## 3. Technology and responsibilities

Use the existing stack where it already satisfies these requirements. The agreed stack is:

- Python for data processing, training, prediction and evaluation.
- FastAPI for backend endpoints.
- React, TypeScript and Vite for the frontend.
- TradingView Lightweight Charts for historical market visualisation, with suitable chart extensions or a compatible chart solution for forecast intervals.
- Parquet for processed market data.
- SQLite for local jobs, forecast records, model metadata and evaluation records.
- Local files for raw archives, model artifacts, manifests and reports.

Check current official dependency documentation during implementation and pin dependency versions.

Keep business logic outside API handlers and UI components. CLI commands and API endpoints must call the same underlying services.

Agents are independently testable components with defined responsibilities and versioned contracts. They do not all need language models.

Forecast-producing specialists use numerical models. LLM agents extract evidence, challenge assumptions and propose experiments through typed tools. Validation, ensemble arithmetic, persistence, scoring, risk constraints and promotions remain deterministic. Keep provider adapters separate from business logic; record provider/model revision, prompts and extraction configuration for reproducibility.

## 4. End-to-end behaviour

The system operates as follows:

1. Import historical BTC/USDT hourly candles.
2. Verify their integrity and report missing or invalid data.
3. Assign observations to training, validation and final-test periods.
4. Build forecasting examples using only information available at each forecast origin.
5. Train candidate price-and-volume models.
6. Select settings, reasoning configurations and specialist combinations using earlier chronological development data; calibrate uncertainty on a separate later development window.
7. Freeze the selected configuration before final-test replay.
8. At each replay origin, generate seven daily forecast points and a weekly summary.
9. The research agents review time-valid evidence and the coordinator validates outputs; it passes one active specialist through or combines accepted specialist distributions under a frozen numerical policy.
10. The publisher saves both specialist and coordinated forecasts.
11. The dashboard displays the saved forecast.
12. As outcomes become available in replay time, the evaluator scores the forecast.
13. In adaptive mode, controlled retraining may use only outcomes that have already matured.
14. Save every model version, forecast and promotion decision for inspection.

A forecast must never be altered after seeing its actual outcome.

## 5. Historical dataset

Primary dataset:

```text
Market: Binance Spot
Symbol: BTCUSDT
Native interval: 1h
Timezone: UTC

Start inclusive: 2022-10-01 00:00:00 UTC
End exclusive:   2026-10-01 00:00:00 UTC
```

Keep these dates configurable, with the above values as the fixed default.

Use public Binance historical archives:

```text
https://data.binance.vision/data/spot/monthly/klines/{symbol}/1h/{symbol}-1h-{YYYY-MM}.zip
```

Consult the official public-data documentation:

```text
https://github.com/binance/binance-public-data
```

Public archive downloads require no account credentials.

Preserve raw archives and verify published SHA-256 checksums.

Support:

- Bounded concurrent downloads.
- Timeouts, bounded retries and backoff.
- Atomic writes.
- Cancellation and resume.
- Reuse of verified files.
- Progress and per-file failures.
- A source manifest recording URL, checksum, retrieval time and status.

Do not start downloading automatically when the app launches. Require an explicit import action.

### Parsing and quality checks

Preserve timestamps, OHLC prices, base and quote volumes, trade counts, taker-buy volumes and source-file identity.

Handle milliseconds in older Binance spot archives and microseconds in archives from January 2025. Normalize to UTC and verify resulting dates.

Validate:

- Schema and finite numeric values.
- Positive prices.
- Non-negative volumes and trade counts.
- Valid OHLC relationships.
- Hourly alignment and chronological ordering.
- Duplicate and conflicting records.
- Missing hours.
- Requested versus actual coverage.

Do not silently forward-fill or manufacture candles.

Distinguish BTC base volume from USDT quote volume.

Completed candle values become available only after their close. Preserve this availability rule throughout feature generation and replay.

Expected complete coverage is 35,064 hourly candles for the default BTC period. Display actual counts and any discrepancy.

## 6. Chronological periods

Use these half-open UTC intervals:

| Period | Start inclusive | End exclusive | Duration |
|---|---|---|---|
| Training | 2022-10-01 | 2025-10-01 | 36 months |
| Validation | 2025-10-01 | 2026-06-01 | 8 months |
| Final test | 2026-06-01 | 2026-10-01 | 4 months |

Expected complete hourly counts:

- Training: 26,304.
- Validation: 5,832.
- Final test: 2,928.

These are raw-observation counts, not counts of eligible forecasting examples.

Use chronological subdivisions of earlier development data for model selection, uncertainty calibration and candidate comparison.

Safeguards:

- Never randomly split time-series examples.
- Fit preprocessing only on the permitted fitting period.
- Training examples’ full future targets must remain inside their permitted period.
- Validation targets must not cross into final test.
- Historical look-back context may extend into an earlier period.
- Incomplete future targets remain unavailable.
- Final-test outcomes must not influence model selection or manual tuning.

If final-test results inform a subsequent design change, label that run as development. Do not continue presenting that same period as an untouched final test.

## 7. Forecast definition

Forecast BTC/USDT spot prices at seven horizons:

```text
+24h, +48h, +72h, +96h, +120h, +144h, +168h
```

At every horizon produce:

- Median price estimate.
- Lower bound for an 80% prediction interval.
- Upper bound for an 80% prediction interval.

For the seven-day summary produce:

- Day-seven median price.
- Return implied by that median relative to the origin price.
- Day-seven prediction interval.
- Probability of a positive seven-day return.
- Probability of a negative seven-day return.

Document how exactly zero returns are handled so probabilities remain coherent.

Use one precise target-price convention. For example, at a UTC forecast origin, use the close of the last completed hourly candle as the origin price; use the corresponding completed-candle close at each future horizon as the target.

Apply this convention consistently in training, prediction, charts and evaluation.

The weekly summary must use the same day-seven output displayed on the chart.

The forecast contains seven daily points. Do not invent an intraday forecast path.

Label the uncertainty band as **pointwise 80% prediction intervals**. It does not represent an 80% guarantee that the entire seven-day path stays within the band.

## 8. Price-and-volume specialist

The specialist receives Bitcoin price and volume history available at the origin.

Inputs may include derived features such as:

- Lagged returns.
- Rolling volatility.
- Rolling trends.
- Recent high-low ranges.
- Volume changes.
- Base or quote volume measures.
- Calendar features.

The Price & Volume specialist excludes Ethereum, derivatives, news, social data and future observations. Separate specialists own those evidence streams. An explicitly labelled augmented-model experiment may combine them; it must not be mislabelled as the pure price/volume reference.

Separate these concepts in code and UI:

- **Training history:** historical examples used to fit the model.
- **Look-back window:** observations used to create inputs for one prediction.
- **Forecast horizon:** seven days into the future.

Do not describe a 90-day look-back as the model’s entire training history.

Evaluate configurable look-back candidates such as 30, 90 and 180 days using development data. These are candidates, not assumed optimal values.

Begin with manageable model families such as regularized regression or gradient-boosted trees. Select using the agreed chronological protocol.

Prefer direct horizon-specific return forecasts. Convert returns to prices using the origin price.

Implement genuine uncertainty estimation and chronological calibration. Prevent quantile crossing.

Generate rise/fall probabilities using a documented probabilistic model or predictive distribution. Do not create arbitrary confidence percentages from a price estimate.

Training must save:

- Model artifact and version.
- Configuration.
- Feature definitions.
- Training cutoff.
- Dataset version.
- Selection and calibration periods.
- Development metrics.

## 9. Forecast contract

Each specialist forecast must contain:

- Forecast ID and run ID.
- Specialist ID.
- Contract and model versions.
- Symbol, market and quote currency.
- Forecast origin.
- Actual generation timestamp.
- Latest input availability timestamp.
- Dataset version.
- Training cutoff.
- Origin price.
- Seven target timestamps and horizon lengths.
- Median forecasts and interval bounds.
- Weekly direction probabilities.
- Central-estimate and interval definitions.
- Configuration identity.
- Quality flags and status.

Validate positive finite prices, ordered intervals, valid probabilities, correct horizons and provenance.

No input availability timestamp may exceed the forecast origin.

Distinguish historical simulated time from actual wall-clock execution time.

## 10. Coordinator and orchestration boundary

Keep the coordinator distinct from the Fund Manager / Orchestrator.

With one forecast-producing specialist, validate its versioned contract, market, horizons, origin and availability; reject invalid output; otherwise create a linked unchanged coordinated forecast with weight 1.0. Label it single-specialist pass-through.

With multiple specialists:

- Require aligned origin, exact target convention, quote currency and evidence cutoff.
- Train non-negative, sum-to-one ensemble weights using development-only out-of-fold forecasts. Compare with equal weights and the best individual specialist. Correlated errors must be measured; agent count is not evidence count.
- Weight distribution samples or CDFs, then derive medians/quantiles from the combined distribution. Do not blindly average interval endpoints or treat medians as expected values. Recalibrate combined uncertainty on a separate chronological window; calculate rise/fall probabilities from the calibrated predictive distribution.
- Freeze specialist versions, feature definitions, prompts, weights and calibration before the evaluated period. Any learned disagreement or regime gate must also be trained and frozen before evaluation.
- The moderator's prose cannot directly replace a price, probability or weight. It can supply validated features, rejection flags or abstention reasons through the approved contract.
- Missing optional evidence triggers a pretested fallback or an unavailable forecast. Do not impute a favourable news opinion, silently remove bad results or retrospectively change weights.
- Record constituent forecasts, accepted/rejected evidence, weights, fallback and disagreement. Save the numerical prediction even when the proposed paper-trade action is Hold.

The Orchestrator schedules tasks and deadlines and gathers results. Later, the Fund Manager assembles a paper strategy proposal and the quantitative risk verdict. Neither can override hard constraints, rewrite saved predictions or place live orders in this scope.

## 11. Publisher and persistence

The publisher saves forecasts before the UI displays them or the evaluator scores them.

Persist:

- Original specialist output.
- Coordinated output.
- Provenance and weights.
- Model and data versions.
- Configuration.
- Origin and generation timestamps.
- Processing status and quality flags.

Forecast predictions are immutable.

Store evaluation records separately and attach actual outcomes without modifying predictions.

Allow users to retrieve and inspect any earlier forecast.

Make jobs and persistence idempotent. Restarting or retrying must not create unintended duplicate forecasts.

## 12. Evaluator

Evaluate specialist and coordinated forecasts separately, even though their predictions initially match.

For each horizon calculate:

- Absolute price error.
- Absolute return error, with units stated.
- Interval coverage.
- Interval width.
- A proper interval score.

For day seven also calculate:

- Direction accuracy.
- Brier score for the positive-return probability.
- Probability calibration summaries when enough samples exist.

Compare against:

- No-change price forecast.
- Historical-frequency direction forecast.
- A documented baseline uncertainty model.

Estimate baseline parameters from earlier available data only.

Show metrics by horizon, model version and replay mode. Include sample counts.

Account for overlapping seven-day windows when reporting statistical uncertainty.

Evaluation states:

```text
Pending
Partially evaluated
Fully evaluated
Unscorable due to missing data
```

Do not substitute a neighbouring candle when the exact target is missing.

An evaluator measures outcomes. It does not retrain a model by itself.

## 13. Historical replay and learning

Provide two separately labelled modes.

### Frozen-model replay

- Select and freeze the model before final test.
- Step through test origins chronologically.
- Generate forecasts using only information available at each origin.
- Score outcomes only when available to the replay clock.
- Keep the model fixed throughout the run.

### Adaptive replay

- Start from a model established before final test.
- Use a predeclared retraining schedule and promotion policy.
- Permit training only on examples whose targets have matured by the simulated cutoff.
- Maintain the same no-future-information rules.
- Keep adaptive results separate from frozen results.

Default forecast cadence: once daily at a documented UTC time.

At the end of the available dataset, horizons without outcomes remain pending or unscorable as appropriate. Do not invent later actuals.

### Controlled retraining

Implement:

1. Candidate training.
2. Comparison with incumbent and baselines on identical earlier held-out cases.
3. Checks of point error and uncertainty quality.
4. Promotion only when predeclared criteria pass.
5. Retention of the incumbent otherwise.
6. Recorded evidence and decision.
7. Rollback to an earlier model version.

Report insufficient evidence honestly.

Coordinator weight learning is enabled only after multiple eligible numerical specialists exist and chronological ensemble validation passes.

## 14. Main dashboard: one desktop workspace

Use the existing shared design tokens and supplied Resource references, adapting layout to the latest agreed design. Desktop only. Do not add the removed Experiment Stages panel.

Keep a compact toolbar for market, saved run/comparison, UTC origin, training configuration, Train & Compare and Predict Next 7 Days. Prediction uses an existing saved model/configuration; it must not silently retrain. Training creates candidates, validates and calibrates them, saves the frozen selection, runs the chosen evaluation protocol and persists outputs. Candidate selection must not use final-test metrics. Display real job progress, cancellation and useful errors.

Combine the upper forecast and lower details into one tabbed workspace occupying remaining width and height. Tabs: Next 7 Days, Predicted vs Actual, Past Test Days, Accuracy & Ranges, All Numbers; add Evidence & Reasoning when the new agents are active. Show only the active graph/view. Move forecast summaries into compact tab content rather than a permanent competing side panel.

Put a compact Models/Specialists selector inside both graph views. Selecting a primary model initially shows it alone; explicitly toggled additional models can be compared. Preserve these choices across graph tabs. Primary prediction is blue, actual prices are white, extra visible models have consistent distinct colours. Uncertainty range is optional for the primary model. Actual visibility is independent of model visibility. Remove the long horizontal model strip.

Mark the forecast origin clearly, preserve history-range selection, pan/zoom, target-aligned tooltips and saved-forecast drill-down. Never fabricate actual prices after the dataset end. Label historical origins instead of calling them today's live forecast. Explain future unavailable outcomes as counts and dates rather than unexplained Pending labels.

Evidence & Reasoning shows compact findings, cited sources, as-of times, counterarguments, unresolved issues and the final numerical decision. Show whether an agent was active, experimental, unavailable or bypassed; never imply a planned agent already ran. Show concise evidence-based rationale, not hidden internal chain-of-thought.

## 15. Agent cards and Inspect behaviour

The existing four components remain the foundation. Add only actually active specialist/research stages to compact status and Inspect views; planned roles must be labelled Planned. Foundation components:

| Component | Responsibility | Example truthful states |
|---|---|---|
| Price & Volume | Train and forecast | Not trained, Training, Ready, Predicting, Failed |
| Coordinator | Validate and pass through | Waiting, Validating, Complete, Rejected |
| Publisher | Save forecasts | Waiting, Saving, Saved, Failed |
| Evaluator | Score available outcomes | Pending, Evaluating, Partial, Complete, Unscorable |

Statuses must correspond to the selected run or forecast. Avoid presenting unrelated jobs as one coherent pipeline. Reasoning stages expose Waiting, Gathering evidence, Reviewing, Validated, Abstained, Unavailable or Failed, with source availability and costs where useful.

The Price & Volume **Inspect** button opens a side drawer or panel. It does not start training.

Show:

- Specialist purpose and permitted inputs.
- Model version and family.
- Training-history dates.
- Training cutoff.
- Look-back window.
- Dataset version.
- Latest input availability.
- Feature definitions and relevant input summary.
- Seven daily forecast values and intervals.
- Weekly probabilities.
- Quality flags.
- Evaluation results where available.

Keep inputs, forecast outputs and later actual outcomes clearly distinguishable.

Provide a close action and preserve the dashboard’s chart selection when the panel closes.

## 16. Forecast chart and weekly summary

The main chart displays:

- Historical BTC price before the origin.
- A labelled forecast-origin divider.
- Seven daily predicted points.
- Pointwise uncertainty shading.
- Actual outcomes as a separate optional overlay.
- Clear legend and USDT price axis.

Support:

- Pan and zoom.
- Crosshair tooltips.
- Selection of a forecast point.
- Historical range selection.
- Forecast and actual visibility toggles.
- Forecast-history selection.

Tooltips show timestamp, horizon, median, interval and actual price when available.

Chart dates, summary dates and stored target timestamps must match exactly.

The weekly summary displays:

- Origin price and time.
- Day-seven target time.
- Median price.
- Implied return.
- Lower and upper interval bounds.
- Rise/fall probabilities.
- Model version.
- Evaluation state.

Changing the selected forecast updates all these components together.

## 17. Historical testing and evaluation UI

Default historical forecast cadence remains once daily at 00:00 UTC; every origin predicts +24 through +168 hours. June through September contains 122 origins per eligible model, not one four-month forecast. Do not change cadence or target definition because of an unfinished verbal suggestion. Frozen and adaptive modes remain separately labelled.

Past Test Days presents saved forecast origins as selectable visual tiles. Explain which forecast was closer than no-change, which baseline was closer, missing outcomes and sample counts. Predicted vs Actual aligns forecast target dates with actual closes at the selected 1–7-day horizon. Accuracy & Ranges shows error, baseline, interval score and calibration; All Numbers provides table and export. Keep older Evaluation and Forecast History accessible.

Score outcomes only when available to the configured historical clock or observed dataset end. Graph/tab navigation does not retrain. Playback and manual clock controls may remain in an advanced Inspect flow; they are not required on the primary workspace. Never disguise missing prices as a failed job.

Evaluation is separate for specialists, augmented models, research-enabled variants and ensemble. Show improvements and regressions rather than a confidence badge inferred from agent consensus. Each saved forecast keeps its original model, prompt, memory, data and ensemble versions.

## 18. Dataset Explorer UI

Preserve the approved dataset page.

Include:

- Symbol, interval, date-range and timezone controls.
- Training, validation and final-test cards.
- Cyan training, amber validation and violet test identification where specified by the reference.
- Real historical candles and volume.
- Split shading and timestamp-aligned boundaries.
- Dataset metadata and quality results.
- Candle inspector.
- Import progress, cancellation and errors.

Selecting a split focuses the chart and table on that period. Allow resetting to full history.

Display actual counts, percentages and volume units.

Keep chart direction colours distinct from split colours. Expose gaps rather than concealing them.

## 19. UI states and responsiveness

Design coherent states for:

- No dataset.
- Importing or incomplete import.
- Quality warnings.
- No trained model.
- Training.
- Replay running.
- Prediction running.
- Forecast ready.
- Awaiting actual outcomes.
- Partial evaluation.
- Failed or cancelled jobs.
- API unavailable.

Never display fictitious learning activity or invented performance.

Disable conflicting actions and explain why. Preserve user selections through refresh where practical.

Desktop must closely match the selected references and latest approved tabbed layout. Mobile implementation and mobile acceptance are excluded. Use horizontal table scrolling where needed.

## 20. API and job interfaces

Provide endpoints for:

- Dataset inventory, metadata and quality.
- Range-filtered candles and paginated inspection rows.
- CSV export.
- Import creation, status and cancellation.
- Training/backtest job creation, status and cancellation.
- Model inventory, metadata and rollback.
- Forecast creation and retrieval.
- Forecast history.
- Replay runs and their saved origins.
- Evaluation results and summaries.
- Agent status for a selected run or forecast.

Use background jobs for imports, training and replay.

Persist job state, prevent conflicting operations and recover truthfully after restart. Do not leave abandoned jobs permanently marked Running.

## 21. Verification and acceptance

Test meaningful cases covering:

- Timestamp-unit normalization.
- Checksums, gaps and conflicting duplicates.
- Exact chronological boundaries.
- Features excluding future information.
- Full target-window eligibility.
- Outcome availability during replay.
- Contract validation.
- Coordinator pass-through equality.
- Immutable forecast persistence.
- Idempotent retries.
- Missing actuals.
- Hand-calculated evaluation metrics.
- Valid probabilities and ordered intervals.
- Candidate promotion and rollback.
- Agreement between chart, summary and stored forecasts.

Run a complete historical replay and report measured results, including failure to beat baselines.

Verify visual fidelity using screenshots at the reference viewport, side-by-side comparisons and overlays. Exclude changing data pixels from strict comparisons while checking chart geometry and styling.

Deliver:

- Complete source code and dependency files.
- Reusable Python CLI.
- Setup and local-run instructions.
- Data manifests and quality reports.
- Versioned model artifacts and configurations.
- Saved example forecasts.
- Replay and evaluation reports.
- Relevant tests.
- Desktop screenshots and reference comparisons.
- Known limitations.

Completion is phased. The existing numerical foundation remains independently usable. The first reasoning milestone requires genuine timestamp-valid news, a trained news forecaster, validated research outputs and a measured ensemble comparison. Later roles are complete only when their contracts, honest UI states, failure paths and evidence gates pass. Absence of predictive improvement must be reported; it is not permission to fabricate a better result.

## 22. Where reasoning belongs

| Role | Reasoning contribution | Deterministic boundary | Activation |
|---|---|---|---|
| Price & Volume / Technical analyst | Explain computed trends and diagnose candidate features | Numerical feature calculations and seven-day forecast | Foundation; narration optional |
| News & Macro analyst | Extract relevant events, novelty, affected asset, event type, sentiment and uncertainty from dated evidence | Schema validation; numerical event-to-return forecaster | First addition |
| Social Sentiment analyst | Separate relevant discussion from spam, bots, duplicates and rumours | Sampling, provenance, numeric aggregation and learned mapping | Later experiment |
| On-chain Fundamentals analyst | Explain network usage, supply, flows and crypto-native fundamentals | Timestamped on-chain measurements and numerical forecasts | Later experiment |
| Derivatives & Liquidity analyst | Interpret positioning, funding, basis and liquidation context | Verified metrics and learned forecasts | Later experiment |
| Multimodal analyst | Extract genuinely additional chart/audio evidence | Timestamped inputs, structured outputs and redundancy tests | Optional research |
| Bull and Bear researchers | Independently propose supporting and contradicting evidence; rebut weak claims | Cannot invent sources, prices, probabilities or causal proof | After news baseline |
| Moderator / Evidence checker | Validate citations, reconcile contradictions, identify missing information and summarise uncertainty | Bounded review; approved flags/features only | With research team |
| Experiment agent | Propose features, numerical settings, extraction schemas and ablations | Allowlisted sandbox tools; no autonomous active-code edits | Offline research |
| Numerical coordinator | Combine validated specialist distributions | Trained weights and calibrated probabilities | After multiple specialists |
| Reflection / Memory agent | Diagnose recurring errors and propose testable prompt/feature hypotheses | Time-scoped memory, versioned candidates, promotion gate | After stable evaluation |
| Trader / Strategy agent | Translate accepted forecasts and evidence into a paper proposal | Predeclared strategy, expected costs and constraint checks | Paper stage |
| Risk-seeking / Neutral / Conservative reviewers | Stress different assumptions and failure scenarios | Cannot change exposure or bypass solver | Paper stage; ablated |
| Quantitative Risk engine | Assess scenarios, CVaR, position/exposure, liquidity and loss limits | Numerical mandatory veto | Before any paper execution |
| Fund Manager / Orchestrator | Delegate, collect evidence and assemble approved proposal | No override of data, risk or execution permissions | Forecast orchestration first; paper later |

Do not duplicate Technical and Price & Volume roles merely to count more agents: shared indicators are computed once and cite the same provenance. Equity financial-statement analysis is an optional future market module, not a required Bitcoin input. Earnings-call audio is not a default BTC source. Chart images derived from existing OHLC are redundant unless an ablation establishes extra value. Persona names are framing devices, not independent risk guarantees.

## 23. Evidence and news data contracts

Begin with permitted publisher feeds and official exchange/regulatory/macro sources. Candidates include CoinDesk reporting, Binance announcements, SEC releases and Federal Reserve releases. Historical archive candidates include GDELT metadata and Event Registry article archives; audit sample coverage, historical versions, timestamps and licence/retention rights before choosing or buying. No provider selection is finalized by this specification.

Collectors are deterministic, bounded and separate from LLM interpretation. Store original permitted payloads, source URL, source type, publication time, first-seen/ingestion time, update time, content hash, content version, language, permissions and availability quality. Deduplicate syndication by event as well as URL; repeated reporting is not repeated independent evidence. Tag promotional content, rumours and confirmations separately. Publication and ingestion time are distinct; an event's scheduled future date does not make its outcome known.

For every forecast origin, use only the evidence version demonstrably available then. Prefer provider-recorded first-seen and revision history. Historic retrieval today is not first-seen at the historic publication time; uncertain availability is flagged/excluded from strict evaluation. News that arrives late becomes available late. Empty news, unavailable source and confirmed absence of relevant news are different states.

LLM extraction outputs: source/evidence IDs, origin cutoff, relevant asset, event type, factual event description, announcement versus realised outcome, polarity, novelty, time horizon, extraction confidence and cited supporting text. Extraction confidence measures evidence interpretation, not probability of a market rise. Link every claim to a stored source span. Unsupported claims are rejected or marked unverified. Treat source content as data, never executable instructions; extraction tools cannot trade or write active configuration.

Train a News & Macro numerical model on chronological event features to forecast the same seven log-return horizons. It may include origin price for converting returns to prices; declare other shared inputs and measure residual correlation with the price/volume specialist. Calibrate it separately. Test both news-only and price-plus-news variants before claiming a separate specialist adds information.

Proposed new storage complements existing files rather than relocating them: data/raw/news/<provider>/ for permitted payloads; data/bundles/news/<version>/ for canonical timestamped article/event records; data/features/news/<version>/ for extraction/features; data/evidence/<version>/ for frozen as-of packets; existing data/versions and SQLite preserve market/model/forecast associations. Use manifests, hashes, atomic publication and a schema version throughout. Training, validation and test are split-labelled immutable views of canonical records; optional exports do not become competing sources of truth. Preserve original article versions and feature/extraction provenance.

## 24. Bounded research, debate and disagreement

Researchers receive the same frozen evidence packet, primary predictions and baseline metrics, but produce their first reviews independently before reading each other. Require factual citations, one clear hypothesis, contradictory evidence, uncertainty and what observation would invalidate the hypothesis. They may explicitly find no reliable advantage; do not force a bullish or bearish trade merely to fill a role.

Default debate budget: one independent review per side, up to two rebuttal rounds, then one moderator report. Configure deadlines and model/token/cost budgets; stop if no new sourced evidence appears. Capped retries and validated output schemas are mandatory. A failed research stage produces an explicit unavailable result and a predeclared baseline fallback, not a persuasive replacement guess.

Moderator records upheld/rejected claims, duplicate evidence, conflicts, missing data and a concise grounded rationale. Verify computational claims with numerical tools. Agreement is not a calibrated probability. Reasoning cannot silently move forecast medians or narrow uncertainty. To affect prices, review outputs must enter a defined feature/gating model trained earlier and tested with/without debate. Until that passes, debate is explanatory only. Abstention can change a paper action to Hold; still record the original forecast and include abstentions in evaluation.

## 25. Reflection and controlled memory

Adapt FinCon-style conceptual verbal reinforcement as a testable candidate mechanism, not unrestricted self-modification. Low-level reflection compares extracted events and numerical inputs with matured prediction errors; high-level reflection examines recurring calibration, regime and paper-strategy failures. Observed association is not proof that a news story caused a price move.

Separate factual episodic memory, model performance summaries and proposed conceptual hypotheses. Store each item's evidence, valid-from time, observation/maturity time, model/prompt version and status: proposed, tested, promoted, rejected or retired. Retrieval at a historic origin excludes later memories and outcomes. Low confidence, contradictions and failed hypotheses remain visible.

A reflection proposes a new prompt/schema/feature candidate offline. The incumbent continues unchanged until candidate extraction, numerical retraining and independent earlier comparison pass. Freeze memory policy and candidate schedule before evaluation; learned policy updates within adaptive evaluation use only already matured outcomes and remain separate from frozen results. CVRF changes prompts/beliefs, not automatically the LLM's weights. Never update a frozen evaluated prompt or retrospectively improve saved output after viewing test outcomes.

## 26. Paper strategy and hard risk constraints

Forecast accuracy is the first objective. Risk-adjusted returns are a later separate objective tested after fees, spread, slippage, latency and execution failures. A seven-day median and rise probability alone are not a complete profitable strategy.

Initial paper scope: BTC spot, unleveraged, long/cash; Hold is valid. Trader proposes instrument, action, size, entry/exit policy, horizon, expiry, supporting evidence and cost assumptions using the frozen forecast. Forecasts and trade decisions are separate immutable records. Model errors and trading results are reported separately; a profitable trade does not prove accurate forecasting.

Contrastive risk reviewers generate scenarios, not discretionary limit changes. A deterministic risk engine validates cash, concentration/exposure, liquidity, order size, expected transaction costs, loss budget, drawdown and data freshness. CVaR is calculated from explicit return scenarios at a stated confidence level; model tail error and stressed scenarios must be assessed. Do not manufacture a full multivariate portfolio/path distribution from seven marginal bounds. Stop-loss is an execution policy, not a guaranteed maximum loss; account for gaps and slippage.

Risk limits, scenario confidence, capital, fees and venue assumptions are required configuration before paper execution; no arbitrary live limits are activated here. Missing/stale inputs, unreliable tail scenarios, constraint violation, unavailable risk service or uncertain execution state block new simulated orders. Fund Manager cannot override a veto. Execution adapter is paper-only by default, idempotent, cancellable and reconciles simulated fills, cash and positions. Future live exchange access is a separately authorized project milestone.

## 27. Honest historical and forward evaluation

Keep the existing 36/8/4-month period definitions and full-target eligibility. News training needs the same three training years and evaluation needs the following validation/test year. Set as-of availability for all sources and transformations. Preprocessing, features, prompt selection, ensemble weights and calibration must be fitted only in their allocated earlier windows. Define ordered fitting/selection/ensemble/calibration folds explicitly, with horizon purging at boundaries and enough eligible samples; if scarce, report insufficient evidence instead of reusing calibration data for tuning.

Existing June–September 2026 outcomes have been inspected, so revised experiments on them are development results. Select a new untouched chronological confirmation window or collect forward predictions. Pre-register cadence, retraining schedule, candidates, hypotheses, selection metric, limits and stopping rules. Compare frozen with scheduled adaptive variants; neither is presumed superior.

Modern LLMs may memorise events and prices from the historical evaluation period. An as-of retrieval filter alone does not eliminate that contamination. Record model revision and documented training cutoff where available; test prompts for unsupported future knowledge; constrain extraction to supplied sources; prefer outcome windows after model/prompt freeze for confirmatory claims. Historic LLM backtests with unknown training cutoff are explicitly exploratory. Do not accept verbal claims of no leakage as proof.

Required ablations: no-change; pure price/volume reference; deterministic news keywords/features; LLM news extraction; augmented model; separate numerical specialists plus equal weights; development-trained weights; single-review versus bull/bear debate; reflection off/on; then each optional specialist. Use identical eligible origins, record source outages and count rejected/missing forecasts rather than selecting favourable dates. Report overlap-adjusted paired uncertainty, horizon-specific MAE/return error, interval score/width/coverage, direction/Brier/calibration, latency, monetary inference cost and fallback rates. Avoid selection across many candidates without an untouched confirmation.

Proposed promotion defaults to freeze before an experiment: at least 1% seven-day MAE improvement against both no-change and the active incumbent; paired seven-day-block-bootstrap 95% interval for candidate-minus-incumbent MAE strictly below zero; no other horizon MAE worsens more than 2%; proper interval score and Brier score no worse than incumbent; measured 80% coverage within 70–90%; at least 60 complete seven-day origins (overlapping origins are not independent samples; assess effective evidence and power); complete provenance; declared cost/latency budget. These are project engineering gates, not claims from a paper, and may be revised only before evaluation. Failure or insufficient power keeps the incumbent. Freeze one selected candidate for fresh confirmation; treat repeated peeking as development. Paper-strategy promotion additionally needs predeclared after-cost risk/return and drawdown gates, not forecast gates alone.

## 28. Jobs, APIs, reproducibility and failure controls

Add thin interfaces for evidence inventory/retrieval, source import and availability, specialist runs, reasoning/research traces, prompt/memory versions, ensemble versions, experiments/ablations and paper risk/decision records. All call shared services; CLI and UI agree. Names and schemas are finalized in phase-one contract review, not guessed into running code by this document.

Every job stores input snapshot IDs, parameters, tool/model revisions, timestamps, validated structured responses, concise cited reasoning summaries, numerical results, cost, latency, cancellations and failure attribution. Do not require or display private internal chain-of-thought. Cache only by evidence/model/prompt/configuration identity; cached later evidence cannot enter earlier forecasts. Prompt inputs should exclude observed future prices and evaluations until a permitted reflection run. Credentials stay outside artifacts; source access and tools are role-limited.

Deterministic calculations, contracts and saved evidence support replay; stochastic provider outputs may not reproduce bit-for-bit, so persist original responses and distinguish exact artifact replay from rerunning an LLM. Retry conservatively, preserve completed specialist outputs, handle partial provider failure and enforce durable jobs/restart recovery. Failed reasoning cannot be silently reported as a complete intelligent pipeline.

## 29. Research alignment and evidence limits

The supplied excerpt combines multiple research ideas; its exact originating document was not identified. This design integrates the applicable patterns, not a claim that all roles are essential or that their reported returns transfer to Bitcoin seven-day price forecasts.

- [TradingAgents: Multi-Agents LLM Financial Trading Framework](https://arxiv.org/abs/2412.20138): inspiration for specialised analysis, contrasting researchers and trading/risk roles. Its financial results are source-reported experiments, not Foresight evidence.
- [FinCon: Conceptual Verbal Reinforcement](https://arxiv.org/abs/2407.06567): inspiration for manager–analyst hierarchy and experience-informed prompt/belief updates. Foresight adds explicit chronology, candidate comparison and rollback requirements.
- [Are Language Models Actually Useful for Time Series Forecasting?](https://arxiv.org/abs/2406.16964): three studied LLM forecasting approaches did not benefit from retaining their LLM component; this motivates ablations rather than assuming improvement.
- [Time-series cross-validation](https://otexts.com/fpp3/tscv.html): supports successive-origin evaluation without future training information.

Paper-inspired roles, crypto adaptations and Foresight-specific engineering gates must be distinguished in reports. No agent count, debate consensus or narrative confidence is presented as empirical calibration.
