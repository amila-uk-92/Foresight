# OpenAI news integration — 11 October 2026

## Current setup

OpenAI is an additive provider, not a Jev impersonation or keyword fallback.
The server and CLI read `.env` at startup, retaining exported-variable precedence.
The local file is ignored by Git and has mode 0600. No subscription credential,
Codex login token, account creation or credit purchase is used.

The user authorized live calls with a £20 ceiling. Current configuration enables
the provider flag, with a **cumulative $20 API usage ceiling** and **$1 per
experiment**. USD20 leaves headroom below GBP20 at the checked GBP/USD rate
of approximately 1.323 on 11 October, including typical VAT headroom; exchange
rates, invoice taxes and card fees are external to this token-usage ledger.
The ledger caps calls made by this Foresight database, not other apps or account
usage. It survives restart, counts pending/uncertain charges and never resets
automatically. No API key is present, so provider status is **not_configured**
and no live request has been made.

## Finish activation

1. Create a restricted project API key in the
   [OpenAI API dashboard](https://platform.openai.com/api-keys) and ensure that
   project has API billing/credits. ChatGPT subscriptions have separate usage.
2. Enter the key locally as `OPENAI_API_KEY` in the project `.env`; never paste it
   into chat, frontend configuration or source control. Leave the configured
   model and spending ceilings unchanged unless intentionally revising the budget.
3. Restart the backend using the README command. Open News & Macro Lab and
   build/select a timestamp-valid packet containing permitted article text.
4. Choose OpenAI, set a small experiment budget (for example $0.01), preview
   pending/cached counts and conservative cost, then explicitly run classification.
5. Inspect saved results, supplied supporting passages, provider model, usage
   and estimated cost. An initial experiment is provider acceptance, not evidence
   of extraction accuracy. Freeze human labels and compare against keywords.

The application makes no calls on navigation, preview, numerical training or
prediction. Collection and paid classification remain separate actions.

## Implemented behavior

- Fixed Responses endpoint, pinned GPT-4o mini snapshot, `store=false`, no tools,
  structured JSON schema and bounded request/output size and timeout.
- Schema/choice/distribution/usage validation; refused, incomplete, invalid or
  unexpected-model responses are rejected. No automatic charged retries.
- Original provider responses persist even when response validation fails.
  Credentials and raw transport exceptions are excluded from error artifacts.
- Atomic per-experiment and cumulative provider reservations prevent concurrent
  runs bypassing the budget. Ambiguous charges keep full reservations.
- Provider/model/question/profile identities separate cache entries. Saved
  classifications produce timestamp-valid feature records, then numerical
  `price_openai` and `news_openai` variants. No language-model price generation.
- Human-labelled OpenAI-vs-keyword evaluation uses identical article versions,
  independently of whether Jev has results. Exports and desktop controls expose
  real saved artifacts. Self-reported probabilities/confidence are explicitly
  uncalibrated; they are not market rise probabilities.

## Acceptance boundary

Fresh verification: **131 backend tests passed** (one upstream Starlette warning),
frontend build/lint passed (eight existing lint warnings and existing large-bundle
warning). Genuine saved-packet API preview returns the pinned OpenAI model and
cost allowance; human-label evaluation truthfully reports insufficient evidence.
The experiment preview declares six variants. The service restarted successfully
on port 8000, with OpenAI status not_configured and total cost zero.

All models, runs, forecasts and evaluations present in the before-OpenAI backup
are retained unchanged. Machine-readable evidence is in
`data/news/openai-acceptance-2026-10-11.json`; backup is
`data/backups/before-openai-2026-10-11.sqlite3`.

Local adapter/failure/budget/cache/evaluation tests use isolated simulated HTTP
transport, not real OpenAI responses in runtime data. Numerical variant tests use
isolated feature fixtures over genuine BTC prices. Live provider acceptance is
blocked until a key and API billing are available. Genuine news-model training
still needs an adequate original-version historical archive.

Research models include a source revision fingerprint. Models produced by the
older news experiment implementation are preserved, but prediction rejects them
after this implementation change; rerun the declared experiment to create a
current model rather than silently rewriting old artifacts. Ordinary price
models and their workflow remain separate.

Sources: [Responses structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[pinned model/pricing](https://developers.openai.com/api/docs/models/gpt-4o-mini),
[subscription/API usage distinction](https://learn.chatgpt.com/docs/pricing),
[dated FX reference](https://www.xe.com/en-us/currencyconverter/convert/?Amount=1&From=GBP&To=USD).
