# Specification conformance audit — 11 October 2026

This is a current code/runtime audit of all 29 sections of `foresight-specification.md`, including earlier implementation. It is not a claim that the whole target system is complete. The authorized milestones are timestamped news/Jev classification and numerical News & Macro experiments. Later ensemble, debate, reflection and trading phases remain planned.

Evidence: 117 backend tests pass; frontend build/lint pass; genuine Federal Reserve collection and desktop workflows verified. `tests/test_news.py` uses isolated, explicitly synthetic news fixtures over real BTC prices; those fixtures never enter runtime storage. Live Jev is not configured. See [acceptance](news-implementation-acceptance.md) and `data/news/acceptance-2026-10-11.json`.

| Spec section | Current status | Evidence / remaining work |
|---|---|---|
| 1 Existing app/design | Implemented foundation | React desktop app, Resource references, existing dataset and Forecast Lab preserved; current screenshots below. No new pixel-perfect reference-overlay claim. |
| 2 Phased specialists | Partial, correctly labelled | Price model remains active; news modules experimental; later agents not presented as successful. |
| 3 Technology/responsibilities | Implemented foundation | `backend/app/news/` services, thin `api/news.py`, shared `cli/news_cli.py`, React `NewsWorkbench.tsx`; deterministic arithmetic separate from classification. |
| 4 End-to-end | Partial | Real collect→packet→keyword classification→saved result→desktop/export works. Paid Jev and genuine historical news forecasts remain externally blocked. |
| 5 Historical dataset | Implemented price dataset | Existing integrity/checksum/missing-hour tests pass; 35,063 real BTC hours, one retained gap. News archive is absent. |
| 6 Chronological periods | Implemented | BTC 36/8/4 boundaries unchanged; news selection/calibration are separate chronological validation subdivisions, full-target eligibility retained. |
| 7 Forecast definition | Implemented | Exact completed-bar origins and seven +24…168-hour targets; intervals/probabilities computed numerically. |
| 8 Price/volume | Implemented | Existing candidate families preserved; augmented research variants have separate specialist IDs and labels. Future-price mutation cannot change fitted news parameters/residuals. |
| 9 Forecast contract | Implemented | Existing validated linked specialist/coordinated contracts generalized to the actual specialist ID; tests cover all four variants. |
| 10 Coordinator | Foundation only | Weight-1 pass-through remains. No learned ensemble, debate influence or distribution mixing enabled. |
| 11 Publisher/persistence | Partial legacy conformance | New news artifacts and forecasts are immutable; old 7,144 forecasts/41 models preserved byte-for-byte in this implementation. **Earlier price-training lifecycle intentionally replaces prior runs, conflicting with v2's retrieve-any-earlier-forecast requirement.** This milestone does not silently change that established workflow. News experiments retain a separate immutable incumbent-output snapshot. |
| 12 Evaluator | Implemented foundation | Exact targets, MAE/return error, interval score/coverage/width, Brier/direction/calibration; matched-origin and paired block intervals for news experiments. |
| 13 Replay/learning | Partial | Existing frozen/adaptive tests pass; new news experiment frozen only, no promotion. Older adaptive promotion defaults differ from section 27's stricter v2 gates and need a separately declared migration. |
| 14 Desktop workspace | Implemented scoped UI | Six tabs retained, inside-graph selectors, blue primary/white actual, expand-graph mode; evidence/news internal views and honest missing states. |
| 15 Inspect | Implemented scoped UI | Existing numerical Inspect retained; saved news model, exact targets and actually-used feature/packet inspection added. Planned researchers remain labelled. |
| 16 Chart/summary | Implemented | One common origin index across news variants; target-aligned actuals, no invented future prices; one snapshot load per bulk graph request. |
| 17 Historical evaluation UI | Implemented scoped UI | Existing test tiles/accuracy/numbers unchanged; new research metrics expandable, graph toggles/horizon/drill-down/export work; 122 origins retained. |
| 18 Dataset Explorer | Preserved/verified | Existing candles, volume, split focus and inspector remain; desktop Dataset renders after restart. |
| 19 UI states | Implemented scoped UI | Not configured, empty, partial, failed and cancel/retry states; partial comparison distinguished from finished job. Desktop only. |
| 20 APIs/jobs | Implemented scoped API | Additive `/api/news` routes, durable serialized jobs/cancellation/restart recovery; retained partial specialist checkpoints. Existing endpoints preserved. CLI is synchronous and uses the same services; do not run CLI mutations concurrently with app jobs. |
| 21 Acceptance | Partial overall | 117 tests and build/lint pass. Genuine news collection/keyword/UI accepted; paid Jev and historical news training not accepted end-to-end. Reference pixel overlays not repeated. |
| 22 Reasoning roles | Partial | Bounded Choice classifier adapter and experimental numerical news specialist implemented. Bull/Bear/moderator and generative explanations not implemented. |
| 23 Evidence/news contracts | Partial external coverage | Immutable versions, clocks, rights, as-of packets, selected supplied passages, exact-identity event clusters and features implemented. Imported first-seen is explicitly provider-attested, not independently audited. Semantic syndication matching is not established; novelty is unknown without earlier-event context. |
| 24 Debate | Planned | No fabricated arguments, forced consensus or influence on prices. |
| 25 Reflection/memory | Planned | No self-modification, future memory or retrospectively changed forecasts. |
| 26 Paper/risk | Planned/not enabled | No orders, account credentials, trading adapter or invented risk approval. |
| 27 Honest evaluation | Partial confirmation | News manifests freeze configuration, article IDs, code revision, incumbent reference and gates. Paired metrics use common complete origins. All historical results labelled development; fresh confirmation unavailable. Gate tests cannot establish real predictive improvement. |
| 28 Failure/reproducibility | Implemented scoped controls | Provider version pinned, original outputs/cache persisted, atomic spend reservations retained after ambiguous failure, redacted errors, artifact integrity checks, partial checkpoints; missing evidence blocks affected variants. |
| 29 Research limits | Aligned design boundary | Agent count/confidence is never treated as accuracy. Full research-inspired hierarchy remains future work. |

## Remaining acceptance gates

1. Supply a permitted October 2022–September 2026 news archive with original-version availability evidence and audit coverage/rights. Current feed: zero historically available versions in training, validation and final test; 13 publication dates in final test are **not** availability evidence.
2. Configure Jev server credentials/enablement and explicitly authorize a capped experiment. Run a bounded real-provider workflow; build and freeze a human-labelled evaluation sample before tuning.
3. Train the genuine news variants on adequate chronological coverage, then collect untouched forward outcomes. The current price-only reference misses by 3,086.15 USDT at seven days versus 3,056.01 for no-change across 116 matured outcomes; it does not beat that baseline.
4. Resolve legacy run-retention and adaptive-gate differences before claiming full specification conformance. Later ensemble/debate/reflection/paper phases remain outside these two milestones.
