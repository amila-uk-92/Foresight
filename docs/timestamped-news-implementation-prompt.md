# Implementation prompt — Modular timestamped news and Jev classification

Implement the following in `/Users/amila/Documents/Foresight Project`. Read this entire prompt before changing code. Deliver working backend and desktop workflows with real persisted records, not mockups. This extends phases 2 and 3 (news evidence/classification) and the relevant phase 7 UI. It does not imply that a trained news forecaster, debate team or ensemble is complete.

## 1. Goal and scope

Add a reusable timestamped-news pipeline and Typesafe Jev classification experiment to Foresight. Users must be able to import news, inspect when each version was available, classify relevant evidence, compare classification quality, and inspect the saved results in the current desktop workspace.

Design this as reusable modules for cryptocurrency, equities, commodities and future asset classes. Initially deliver a genuine Bitcoin news workflow. Make adding a stock or gold instrument a documented registry/configuration and provider-adapter extension, without editing shared processing or UI logic. Do not claim working stock/gold integration until real adapters and data are verified.

Classification quality and forecasting accuracy are separate outcomes. Jev judges supplied text; numerical models predict prices. This milestone must not silently alter current forecasts or claim improved predictive accuracy.

Do not enable trading, purchase news subscriptions, create provider accounts, activate automatic credit refills, or replace the existing forecasting protocol. Use configured provider access within an explicit experiment budget. Default external AI calls to disabled until credentials, access and a budget exist; implement all independent work while unavailable and report that integration as unverified.

## 2. Inspect and preserve the existing architecture

Read:

- `docs/foresight-specification.md`, particularly sections 22–28.
- `docs/multi-agent-implementation-plan.md`, phases 1–3 and 7.
- `docs/adding-a-market.md`.
- `backend/app/markets/spec.py`, `registry.py`, `calendar.py`, `sources.py` and market registration.
- Existing dataset bundles, snapshots, SQLite persistence, forecasting contracts, jobs and API services.
- `frontend/src/components/ForecastLabView.tsx`, `ModelComparison.tsx`, `LabChart.tsx`, `LabVisuals.tsx`, frontend types and layout styles.

Verify the active implementation: old reports may describe different model subsets or UI layouts. Reuse existing market selection, durable jobs, service boundaries and conventions. Identify genuine gaps before extending them. Preserve raw archives, current pointers, models, forecasts and existing APIs. Use additive, migration-safe persistence changes and preserve old records.

## 3. Modular contracts and registry extensions

Create versioned typed contracts and interfaces for:

- NewsSource: discovery, retrieval/import, pagination/cursors, normalization, availability evidence, revisions, rate limits and content/retention rights.
- NewsClassifier: classify supplied evidence using a versioned taxonomy and asset profile; return structured results and usage.
- EvidenceStore: immutable source versions, packet manifests, article-to-instrument associations and provenance.
- EvidencePacketBuilder: select demonstrably available evidence at a forecast origin.
- NewsFeatureBuilder: turn validated classifications into numerical features, with documented missing-data semantics.
- ClassificationExperimentService: immutable experiment definition, matched inputs, labels, metrics, cost and results.

Keep collection, classification, aggregation, evaluation and UI transport separate. Shared services serve API and CLI. Provider adapters contain provider-specific formats, authentication and failure handling; shared services contain no Binance/CoinDesk/Typesafe assumptions.

Extend existing MarketSpec/registry composition rather than creating a competing market registry. Add asset profiles with canonical instrument IDs, asset class, venue, currency, identifiers/aliases, entity context, news scopes, taxonomy and feature configuration. Symbol text alone is insufficient: distinguish similarly named instruments and share classes. Reject ambiguous mappings; record unsupported or unknown assets.

Gold profiles must identify the actual instrument, such as spot XAU/USD, a specific futures contract, or an ETF. Do not treat these as interchangeable. Equity profiles must identify their exchange and issuer. Macro news may map to multiple instruments through versioned relevance records; store source content once rather than duplicating it for each market.

Use market calendars for origins, target dates, lookbacks and news windows. Preserve Bitcoin's existing daily/+24–168-hour behavior. Do not hard-code that behavior for exchange-session assets: configure calendar versus trading-session horizons, timezone, DST, holidays and close availability. Derive display labels from the market contract. News outside trading hours becomes usable at the next eligible origin once available.

## 4. Genuine news ingestion and storage

Implement a real licensed/permitted news source adapter and a generic local JSON/JSONL import adapter. Inspect current official feeds/access terms before choosing the initial feed. A current RSS feed supports forward collection; it does not demonstrate a four-year archive. Do not fabricate historical coverage or bypass paid access.

Store, where available:

- Stable provider/article IDs, canonical URL, publisher and source type.
- Headline, language and permitted body or snippet; identify exactly what was classified.
- Publication time, provider first-seen time, ingestion time, update time and event date as distinct UTC fields.
- Timestamp provenance, precision, timezone assumptions and availability-quality flag.
- Original permitted payload, content hash, content version and predecessor/revision link.
- License/retention/full-text access metadata, import job and retrieval errors.

Never infer historical first-seen from today's retrieval or simply trust a publication date as proof that the current text existed then. For live collection, ingestion time is a conservative availability bound. For retrospective imports, use independently supported provider/version availability; otherwise mark exploratory/unknown and exclude from strict replay. Compute effective availability deterministically and document its policy.

Use the specification's proposed raw/news, bundles/news, features/news and evidence storage areas, consistent with existing atomic manifests and SQLite associations. Store canonical source versions once and expose split-labelled views. Use content/URL deduplication plus separately evaluated event clusters; preserve individual sources and avoid counting syndicated copies as independent events.

Implement incremental import, idempotent retries, cooperative cancellation, progress, restart recovery and partial failure reporting. Limit payload size and network timeouts. Treat imported text as untrusted data, not agent instructions. Preserve permitted evidence spans; never fabricate full text when only a headline is available.

## 5. Point-in-time evidence packets

Each packet records market/instrument, origin, lookback, availability policy, included article version IDs, excluded counts/reasons, taxonomy revision and a hash.

Include only versions with effective availability at or before origin. Later revisions must never replace the earlier text in a saved packet. Late-arriving news enters later packets. Apply the same rule to duplicate clusters, relevance profiles, reference context, extraction configuration and any supplied earlier-news context used for novelty judgments.

Keep these states distinct: no relevant news with adequate coverage, no source coverage, missing body, unavailable provider, uncertain historical availability, and classification not run. Missing evidence is not neutral sentiment.

For historical coverage, audit the agreed October 2022–September 2026 period: three training years plus validation/testing. If a permitted archive is unavailable, finish forward collection/import and report historical validation as blocked. Do not invent data or subscribe automatically.

## 6. Typesafe Jev adapter

Read current official documentation before implementation:

- https://docs.typesafe.ai/introduction/quickstart
- https://docs.typesafe.ai/models
- https://docs.typesafe.ai/confidence
- https://docs.typesafe.ai/model-jaggedness/jev-1.13
- https://docs.typesafe.ai/cookbooks/citation_check

Use the Python SDK or backend HTTP adapter. Keep the API key server-side in environment/secret configuration. Pin an available explicit model version and dependency version; record the actual response model. Do not rely on a moving latest alias for an experiment.

Use narrow atomic questions with bounded answer sets and an explicit unknown/insufficient-evidence option. Initial classifications:

- Relevance to the supplied instrument profile.
- Event category: regulatory, monetary/macro, security incident, exchange/market infrastructure, institutional flows/adoption, issuer/corporate event, supply/network, or other/unknown, as appropriate for the asset class.
- Article framing: positive, negative, mixed, neutral or insufficient evidence; this is not a predicted market return.
- Whether the supplied text describes an announcement, realised event, commentary or unverified claim.
- Novelty relative to explicitly supplied time-valid earlier evidence; unknown if that context is missing.

Batch independent questions against one concise article/context packet. Respect documented context limits. Do not ask Jev to generate summaries, source text, citations, numerical prices, exact arithmetic or date ordering. Select supporting passage IDs from supplied candidates with none/unsupported options; validate that selected passages actually exist. Fixed UI templates may explain classifications using verbatim cited text. Free-form bull/bear reasoning belongs to a later generative-agent milestone.

Persist probabilities, Choice/Score confidence where returned, typed outputs, original response, input hash, criteria/prompt/taxonomy revisions, selected passages, article/profile IDs, provider/model, request time, usage, estimated cost, latency and errors. Noul responses have no separate confidence property: do not invent one. Classification confidence must not be presented as probability of a price rise or source credibility.

Implement configurable request/token/spending caps, bounded retries and backoff, timeouts, cancellation and concurrency limits. Reserve estimated budget atomically before dispatch, reconcile actual usage, and account conservatively for uncertain retry charges. Display pricing assumptions and separate estimated from provider-confirmed cost. Never assume free output means free requests or guaranteed promotional credits.

Cache by content version, provider/model, questions, taxonomy, profile and permitted context identity. Later information must not enter earlier feature packets through cache reuse. Save stochastic responses for exact artifact replay; rerunning the provider is a distinct operation.

## 7. Classification and timestamp experiments

Before external calls, show an experiment preview: source scope, market, dates, article count, availability policy, question/model versions, estimated tokens/cost and hard budget. Starting collection and starting paid classification are distinct actions.

Provide a deterministic keyword/rule classifier as a named comparator. It is not a fabricated Jev fallback. Run both on identical eligible article versions; preserve outages, rejected inputs and missing classifications in result counts.

Support a versioned manually labelled evaluation sample, sourced from genuine articles, including macro stories, irrelevant items, ambiguous instrument names, rumours, revisions and missing text. Preserve annotation provenance. Freeze a separate evaluation sample before tuning questions or thresholds; report annotation disagreement and insufficient sample size.

Report per-category precision/recall, macro-F1, abstention/coverage, accepted-decision accuracy, probability calibration/Brier metrics where appropriate, citation-support quality, latency, tokens, cost and failures. Include confusion matrices and sample sizes. Do not equate thresholding with proof of calibration. Exact quote matching is deterministic; semantic support checks remain fallible judgments.

Prove that revised articles, delayed ingestion, timestamp errors, future reference context and source injection cannot silently pass strict evidence filtering. Distinguish historical exploratory extraction from live point-in-time extraction: model memorization of past events remains a contamination risk.

Build versioned numerical features and link them to origin packets: relevant-event counts, category distributions, framing probabilities, novelty and availability/coverage indicators. Configure aggregation windows by market calendar, deduplicate event counts, and fit transformations only on earlier data. Record revisions and missingness explicitly.

This milestone ends at validated classification, feature artifacts and UI integration. Do not train/promote a news price forecaster unless separately included in the task's authorized scope. Export reproducible matched-origin inputs for a later experiment comparing price-only, price plus keyword news, and price plus Jev news. Future predictive claims require chronological fitting/selection/calibration, matured exact targets, overlap-aware uncertainty and untouched forward confirmation. Preserve the existing 36/8/4 boundaries for BTC; already-inspected test outcomes remain development results.

## 8. Desktop integration

Extend the current workspace; retain its five existing tabs, chart space, model toggles, blue primary predictions, white actuals, uncertainty controls, history ranges, drill-down and export.

Add Evidence & Reasoning with compact internal views for:

- News: real article timeline/list, source and market filters, publication/availability timestamps, version and eligibility badges, classification and source drill-down.
- Forecast evidence: immutable packet tied to the selected forecast, where an association exists, showing included/excluded records, origin cutoff, features and provenance.
- Experiments: keyword-versus-Jev metrics, confusion matrix, coverage, cost/latency and real sample inspection.

Keep research-origin news packets separate from forecasts that never used news. For legacy forecasts show “No news evidence recorded for this forecast”; a newly built exploratory packet is explicitly labelled and must not become fabricated forecast provenance. Show news as experimental until a news forecasting model is actually validated.

Expose import/collect, build packet, preview/classify, cancel, inspect and export controls with real durable jobs. Use the existing selected market and saved-run context consistently; hide unsupported capabilities with an explanation. Distinguish collection window from forecast horizon. Tab changes and filters must not classify, retrain or incur API cost.

Explain every label plainly. Separate event interpretation, evidence availability, prediction uncertainty and trade eligibility. Display Planned, Not configured, Experimental, Running, Complete, Partial, Failed, Cancelled and Budget exhausted only when appropriate. Missing API credentials must not appear as an endless spinner. Do not fabricate bull/bear reports or agent-success cards.

Handle API errors with retry actions and useful messages. Preserve stored results during outages; distinguish legacy absence from unexpected missing records. Cancel superseded fetches on market/run switches. Sanitize article rendering, validate outbound links, keep secrets out of exports, and implement keyboard-accessible tabs/toggles. Desktop only.

## 9. Verification and acceptance

Run relevant backend tests, frontend build/lint and genuine desktop browser workflows. Add meaningful tests for:

- Publication versus first-seen versus ingestion; UTC/DST/session boundaries.
- Retroactively edited content and late arrival; unknown availability exclusion.
- Idempotent imports, deduplication, versioned packets and restart recovery.
- Ambiguous instrument IDs, multi-market news and asset-specific taxonomies.
- Classification schemas, Noul confidence absence, unsupported source passages.
- Cached later-context leakage, injection content, provider failure, timeout and cancellation.
- Concurrent budget reservations, retry accounting and exhausted/disabled-provider states.
- Matched classifier inputs, missing-data features, exports and immutable legacy forecasts.

Test modules using clearly labelled fixtures; do not expose synthetic fixture data as production records. Verify stock/calendar and gold-profile extension contracts in tests without claiming those feeds are live.

At 1440×900 and 1672×941, capture real screenshots showing the six-tab workspace, imported articles, timestamp/eligibility inspection, classifier results, experiment metrics and legacy/no-key/error states. Test market switches and ensure graphs fill their allocated space.

With configured access/budget, perform one bounded real collection/import → evidence packet → Jev classification → persisted experiment → UI inspection → export workflow. Restart the service after implementation and verify health, saved records and job recovery. If credentials or source rights are unavailable, complete independent work and clearly report the exact unverified stage; do not claim end-to-end acceptance.

Update the market-extension guide, setup/configuration documentation and implementation acceptance report. Include source licensing/availability limitations, configured provider/model revisions, costs, samples, quality results, screenshots and completed/remaining checklist.

Completion requires genuine timestamped news, an interchangeable classifier interface, verified as-of filtering, persisted results, honest UI integration and regression checks. It does not establish improved forecasting accuracy or completion of the full multi-agent system.
