"""Shared import, evidence, extraction and classification experiment services."""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import numpy as np
from backend.app.config import DATA_DIR
from backend.app.storage import now, atomic_json
from backend.app.markets import get_market, markets
from backend.app.news.store import NewsStore, digest
from backend.app.news.contracts import ArticleInput, utc
from backend.app.news.sources import SOURCES
from backend.app.news.classifiers import KeywordClassifier, JevClassifier, classifier_identity, CATEGORIES, MODEL, PRICE


def profile(market):
    p = {"instrument_id": market.symbol, "asset_class": market.asset_class, "venue": market.venue, "currency": market.quote_asset, "name": market.display_name,
         "aliases": [market.symbol, market.display_name, market.base_asset], "taxonomy": "news-taxonomy/1"}
    if market.asset_class == "crypto":
        p["aliases"] += {"BTC": ["bitcoin"], "ETH": ["ethereum"]}.get(market.base_asset, [])
    extra = market.extra.get("news_profile", {})
    if any(k in extra and extra[k] != p[k] for k in ("instrument_id", "asset_class", "venue", "currency")):
        raise ValueError("News profile cannot override canonical market identity")
    p.update(extra)
    if not isinstance(p["aliases"], list) or not all(isinstance(a, str) and a.strip() for a in p["aliases"]):
        raise ValueError("News aliases must be explicit nonempty strings")
    p["version"] = digest(p)
    return p


def window_start(market, origin, days):
    # Uses the same configured calendar as targets, including session calendars.
    calendar = market.calendar
    if calendar.kind == "continuous":
        return calendar.horizon_target(origin, -days)
    # Existing session adapters only promise positive horizon steps.
    cursor = origin
    for _ in range(days):
        cursor -= 86400
        for guard in range(370):
            if calendar.is_origin(cursor):
                break
            cursor -= 86400
        else:
            raise ValueError("Calendar has no prior scheduled origin")
    return cursor


def event_clusters(articles):
    """Conservative exact identity clustering; no invented semantic consensus."""
    parent = {a["id"]: a["id"] for a in articles}
    def find(id):
        while parent[id] != id:
            parent[id] = parent[parent[id]]
            id = parent[id]
        return id
    owners = {}
    for a in articles:
        u = urlsplit(a["url"])
        query = [(k,v) for k,v in parse_qsl(u.query) if not k.lower().startswith('utm_')]
        canonical = urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path,urlencode(sorted(query)),""))
        keys = [("url",canonical),("content",a["content_hash"]),("headline",re.sub(r"\W+"," ",a["headline"].lower()).strip())]
        if a.get("event_id"):
            keys.append(("attested_event",a["event_id"]))
        for key in keys:
            if key in owners:
                parent[find(a["id"])] = find(owners[key])
            owners[key] = a["id"]
    groups = {}
    for a in articles:
        groups.setdefault(find(a["id"]), []).append(a)
    return [sorted(group,key=lambda a:(a["effective_available_at"],a["publisher"],a["id"])) for group in groups.values()]


class NewsService:
    def __init__(self, store, jobs=None, root=None):
        self.records = NewsStore(store, Path(root or DATA_DIR))
        self.store, self.jobs = store, jobs

    def status(self):
        return {"schema_version": "news/1", "sources": [{"id": k, "kind": "forward RSS", "url": v.url} for k, v in SOURCES.items()],
                "classifiers": [{"id": "keywords", "state": "configured", "model": KeywordClassifier.version, "label": "Deterministic rules (not calibrated)"},
                                {"id": "jev", "state": "configured" if os.getenv("TYPESAFE_API_KEY") and os.getenv("FORESIGHT_JEV_ENABLED") == "1" else "not_configured", "model": MODEL, "price_per_million_input_usd": PRICE}],
                "markets": [profile(m) for m in markets()], "article_count": len(self.records.list("article")), "imported_providers": sorted({r["provider"] for r in self.records.list("article")}),
                "trading": "not_enabled", "news_forecasting": "experimental", "historical_notice": "No historical coverage is inferred from forward feeds or publication dates."}

    def coverage(self, symbol):
        market = get_market(symbol)
        articles = self.records.list("article")
        return {"symbol": market.symbol, "periods": {name: {"start": split["start"].isoformat(), "end_exclusive": split["end"].isoformat(),
            "published_versions": sum(split["start"].isoformat() <= a["published_at"] < split["end"].isoformat() for a in articles),
            "available_versions": sum(split["start"].isoformat() <= a["effective_available_at"] < split["end"].isoformat() for a in articles),
            "source_continuity": "not_established"} for name, split in market.splits.items()},
            "provider_attestations_independently_audited": False, "notice": "Version counts are not evidence of complete source coverage; publication alone is not historical availability"}

    def ingest(self, rows, provider="local", check=lambda: None, progress=lambda *a: None, collected=False):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", provider):
            raise ValueError("Invalid provider ID")
        ids, errors = [], []
        for j, input in enumerate(rows):
            check()
            try:
                a = input if isinstance(input, ArticleInput) else ArticleInput.model_validate(input)
                a = a.model_dump()
                observed = now()
                if a["published_at"] > observed or a["updated_at"] and a["updated_at"] > observed:
                    raise ValueError("Publication/update time is in the future; scheduled events use event_at")
                first = a["provider_first_seen_at"]
                if first and not a["availability_evidence"]:
                    raise ValueError("Provider first-seen requires explicit version-specific availability evidence")
                if first and first > observed:
                    raise ValueError("First-seen time is in the future")
                available = max(first, a["updated_at"] or first, a["published_at"]) if first else observed
                if available > observed:
                    raise ValueError("Publication/update time is in the future")
                version = digest({"provider": provider, **a})
                try:
                    existing = self.records.get("article", version)
                    ids.append(existing["id"])
                    continue
                except ValueError:
                    pass
                predecessor = next((x["id"] for x in self.records.list("article") if x["provider"] == provider and x["provider_article_id"] == a["provider_article_id"]), None)
                row = {**a, "id": version, "schema_version": "article/1", "provider": provider, "ingested_at": observed,
                       "effective_available_at": available, "availability_quality": "provider_attested" if first else "observed" if collected else "unknown_historical",
                       "availability_note": "Imported provider availability is an explicit supplied attestation, not independently verified by Foresight" if first else "Only current ingestion is verified; no historic availability claim",
                       "content_hash": digest({"headline": a["headline"], "text": a["text"]}), "predecessor_id": predecessor}
                atomic_json(self.records.root / "raw/news" / provider / (version + ".json"), a)
                ids.append(self.records.put("article", row)["id"])
            except ValueError as e:
                errors.append({"row": j, "error": str(e)})
            progress("Imported news", 100 * (j + 1) / len(rows))
        return {"state": "partial" if errors and ids else "failed" if errors else "complete", "article_ids": ids, "errors": errors}

    def collect(self, source, check=lambda: None, progress=lambda *a: None):
        if source not in SOURCES:
            raise ValueError("Unknown news source")
        return self.ingest(SOURCES[source].collect(check), source, check, progress, collected=True)

    def packet(self, symbol, origin, lookback_days=7, policy="strict", article_ids=None):
        market = get_market(symbol)
        origin = utc(origin)
        start = __import__("datetime").datetime.fromtimestamp(window_start(market, __import__("datetime").datetime.fromisoformat(origin).timestamp(), lookback_days), __import__("datetime").timezone.utc).isoformat()
        included, excluded = [], []
        rows = [self.records.get("article", id) for id in article_ids] if article_ids is not None else self.records.list("article")
        for a in rows:
            available = a["effective_available_at"]
            reason = None
            if policy == "exploratory" and a["availability_quality"] == "unknown_historical":
                available = max(a["published_at"], a["updated_at"] or a["published_at"])
            if available > origin:
                reason = "available_after_origin"
            elif available <= start:
                reason = "outside_window"
            elif policy == "strict" and a["availability_quality"] == "unknown_historical" and origin < a["ingested_at"]:
                reason = "unknown_historical_availability"
            if reason:
                excluded.append({"id": a["id"], "reason": reason})
            else:
                included.append((a, available))
        # Select the newest eligible version only; never the latest future version.
        versions = {}
        for a, available in included:
            key = (a["provider"], a["provider_article_id"])
            if key not in versions or (available, a["ingested_at"]) > (versions[key][1], versions[key][0]["ingested_at"]):
                if key in versions:
                    excluded.append({"id": versions[key][0]["id"], "reason": "superseded_as_of_origin"})
                versions[key] = (a, available)
            else:
                excluded.append({"id": a["id"], "reason": "superseded_as_of_origin"})
        ids = sorted(x[0]["id"] for x in versions.values())
        record = {"schema_version": "evidence-packet/1", "symbol": market.symbol, "origin": origin, "window_start": start,
                  "lookback_days": lookback_days, "policy": policy, "profile": profile(market), "article_ids": ids,
                  "excluded": sorted(excluded, key=lambda x: x["id"]), "coverage_state": "articles_observed" if ids else "coverage_unknown",
                  "limitations": ["Source continuity is not established; an empty packet is not proof of no relevant news", "Provider attestations need source audit", "Historical AI extraction can contain model memorization"]}
        record["id"] = digest(record)
        return self.records.put("packet", record)

    def preview(self, packet_id, classifier="keywords", max_articles=100):
        packet = self.records.get("packet", packet_id)
        identity = classifier_identity(classifier, packet["profile"])
        selected = packet["article_ids"][:max_articles]
        pending = []
        for id in selected:
            key = digest({"article": id, "classifier": identity})
            try:
                self.records.get("classification", key)
            except ValueError:
                pending.append(id)
        return {"packet_id": packet_id, "classifier": classifier, "article_ids": selected, "pending_ids": pending,
                "cached_count": len(selected) - len(pending), "omitted_count": max(0, len(packet["article_ids"]) - len(selected)),
                "conservative_max_cost_usd": len(pending) * 24000 * PRICE / 1_000_000 if classifier == "jev" else 0,
                "pricing_status": "estimated maximum; tokens depend on input; output free is not free input", "model": MODEL if classifier == "jev" else KeywordClassifier.version}

    def classify(self, packet_id, classifier="keywords", budget_usd=0, max_articles=100, check=lambda: None, progress=lambda *a: None):
        preview = self.preview(packet_id, classifier, max_articles)
        packet = self.records.get("packet", packet_id)
        id = __import__("uuid").uuid4().hex
        if classifier == "jev":
            if not os.getenv("TYPESAFE_API_KEY") or os.getenv("FORESIGHT_JEV_ENABLED") != "1":
                raise ValueError("Jev not configured; keyword comparison remains available")
            self.records.budget(id, budget_usd)
        adapter = KeywordClassifier() if classifier == "keywords" else JevClassifier(self.records)
        results, errors = [], []
        identity = classifier_identity(classifier, packet["profile"])
        for i, article_id in enumerate(preview["article_ids"]):
            check()
            key = digest({"article": article_id, "classifier": identity})
            try:
                try:
                    result = self.records.get("classification", key)
                except ValueError:
                    article = self.records.get("article", article_id)
                    requested_at = now()
                    out = adapter.classify(article, packet["profile"], {"budget_id": id}, check)
                    passage = out["answers"]["support"]["choice"]
                    result = self.records.put("classification", {"id": key, "schema_version": "news-classification/1", "article_id": article_id,
                        "symbol": packet["symbol"], "profile_version": packet["profile"]["version"], "classifier": classifier, "classifier_identity": identity,
                        "question_version": adapter.version, "requested_at": requested_at, "input_hash": digest({"article": article_id, "profile": packet["profile"], "classifier": identity}),
                        "supporting_passage": {"id": passage, "text": article.get(passage) if passage in {"headline", "text"} else None, "semantic_support": "not_independently_verified"},
                        "novelty": "unknown; no earlier-event context supplied", "original_response": out, **out})
                results.append(result["id"])
            except ValueError as e:
                errors.append({"article_id": article_id, "error": str(e)})
            progress("Classifying news", 100 * (i + 1) / max(1, len(preview["article_ids"])))
        experiment = {"id": id, "schema_version": "classification-experiment/1", "packet_id": packet_id, "symbol": packet["symbol"], "classifier": classifier,
                      "classification_ids": results, "errors": errors, "preview": preview, "state": "failed" if errors and not results else "partial" if errors or preview["omitted_count"] else "complete",
                      "budget": self.records.budget(id) if classifier == "jev" else None,
                      "evaluation_state": "not_labelled; freeze a human-labelled evaluation set before tuning"}
        return self.records.put("classification_experiment", experiment)

    def label(self, values):
        self.records.get("article", values["article_id"])
        get_market(values["symbol"])
        if values["category"] not in CATEGORIES:
            raise ValueError("Unknown category")
        return self.records.put("label", {"schema_version": "news-label/1", **values})

    def classification_evaluation(self, packet_id):
        packet = self.records.get("packet", packet_id)
        labels = [x for x in self.records.list("label") if x["symbol"] == packet["symbol"] and x["article_id"] in packet["article_ids"]]
        by_article = {}
        conflicts = []
        for label in labels:
            if label["article_id"] in by_article and any(label[k] != by_article[label["article_id"]][k] for k in ("relevance", "category", "framing")):
                conflicts.append(label["article_id"])
            by_article[label["article_id"]] = label
        rows = {}
        classifications = self.records.list("classification")
        common = set(by_article) - set(conflicts)
        maps = {name: {x["article_id"]: x for x in classifications if x["classifier"] == name and x["symbol"] == packet["symbol"] and x["profile_version"] == packet["profile"]["version"]} for name in ("keywords", "jev")}
        maps = {name: {id: x for id, x in items.items() if x["classifier_identity"] == classifier_identity(name, packet["profile"])} for name, items in maps.items()}
        # Comparing different labelled subsets would confound classifier quality
        # with article difficulty. Report only a paired frozen sample.
        matched = common & set(maps["keywords"]) & set(maps["jev"])
        for name, items in maps.items():
            confusion, brier = {}, []
            ids = sorted(matched)
            for key in ("relevance", "category", "framing"):
                matrix = {}
                for id in ids:
                    predicted = items[id]["answers"][key]["choice"]
                    actual = by_article[id][key]
                    matrix.setdefault(actual, {})[predicted] = matrix.setdefault(actual, {}).get(predicted, 0) + 1
                    probs = items[id]["answers"][key]["probabilities"]
                    brier.append(sum((p - float(option == actual)) ** 2 for option, p in probs.items()))
                scores = []
                per_category = {}
                for category in set(matrix) | {k for v in matrix.values() for k in v}:
                    tp = matrix.get(category, {}).get(category, 0)
                    actual_count = sum(matrix.get(category, {}).values())
                    predicted_count = sum(v.get(category, 0) for v in matrix.values())
                    precision, recall = tp / max(1, predicted_count), tp / max(1, actual_count)
                    f1 = 2 * precision * recall / max(1e-12, precision + recall)
                    scores.append(f1)
                    per_category[category] = {"precision": precision, "recall": recall, "f1": f1}
                confusion[key] = {"matrix": matrix, "per_category": per_category, "macro_f1": float(np.mean(scores)) if scores else None}
            rows[name] = {"sample_count": len(ids), "article_ids": ids, "metrics": confusion, "multiclass_brier": float(np.mean(brier)) if brier else None,
                          "abstentions": sum(items[id]["answers"]["relevance"]["choice"] == "unknown" for id in ids),
                          "cost_usd": sum(items[id].get("cost_usd", 0) for id in ids), "latency_seconds": sum(items[id].get("latency_seconds", 0) for id in ids)}
            accepted = [id for id in ids if items[id]["answers"]["relevance"]["choice"] != "unknown"]
            rows[name].update(accepted_count=len(accepted), accepted_decision_accuracy=float(np.mean([items[id]["answers"]["relevance"]["choice"] == by_article[id]["relevance"] for id in accepted])) if accepted else None,
                              supported_passage_fraction=float(np.mean([items[id]["answers"]["support"]["choice"] != "none" for id in ids])) if ids else None,
                              support_note="Selected supplied passage exists; semantic support has not been human verified",
                              input_tokens=sum(items[id].get("usage", {}).get("input_tokens", 0) for id in ids))
        # Freeze labels and classification IDs: later annotations never rewrite this evaluation.
        return self.records.put("classification_evaluation", {"schema_version": "classification-evaluation/1", "packet_id": packet_id,
            "label_ids": sorted(x["id"] for x in labels), "classification_ids": sorted(items[id]["id"] for items in maps.values() for id in matched), "conflicting_article_ids": sorted(set(conflicts)), "results": rows,
            "matched_article_ids": sorted(matched),
            "status": "insufficient_evidence" if len(matched) < 30 else "development",
            "note": "Human labels are required; this is extraction quality, not forecasting accuracy. Freeze this sample before tuning."})

    def features(self, packet, classifier):
        identity = classifier_identity(classifier, packet["profile"])
        names = ["event_count", "coverage_observed", "missing_classification_fraction", "positive", "negative", "mixed", "unknown_framing", *CATEGORIES, "announcement", "realised", "commentary", "unverified", "unknown_event_status", "novelty_unknown"]
        vector = np.zeros(len(names))
        used, missing, rejected, classified = [], [], [], {}
        articles = [self.records.get("article", id) for id in packet["article_ids"]]
        clusters = event_clusters(articles)
        for article in articles:
            id = article["id"]
            key = digest({"article": id, "classifier": identity})
            try:
                c = self.records.get("classification", key)
            except ValueError:
                missing.append(id)
                continue
            used.append(key)
            a = c["answers"]
            if a["support"]["choice"] == "none":
                missing.append(id)
                rejected.append(key)
                continue
            classified[id] = a
        for cluster in clusters:
            # Same representative for all classifier variants, chosen by clocks,
            # never by a favourable extracted opinion or a later price outcome.
            a = classified.get(cluster[0]["id"])
            if not a:
                continue
            relevance = a["relevance"]["probabilities"]["relevant"]
            vector[0] += relevance
            for category in ("positive", "negative", "mixed", "unknown_framing", *CATEGORIES):
                question = "framing" if category in {"positive", "negative", "mixed", "unknown_framing"} else "category"
                value = "unknown" if category == "unknown_framing" else category
                vector[names.index(category)] += relevance * a[question]["probabilities"].get(value, 0)
            for status in ("announcement", "realised", "commentary", "unverified", "unknown_event_status"):
                vector[names.index(status)] += relevance * a["event_status"]["probabilities"].get("unknown" if status == "unknown_event_status" else status, 0)
        vector[1] = float(bool(packet["article_ids"]))
        vector[2] = len(missing) / max(1, len(packet["article_ids"]))
        vector[names.index("novelty_unknown")] = float(bool(packet["article_ids"]))
        record = {"schema_version": "news-features/2", "packet_id": packet["id"], "symbol": packet["symbol"], "origin": packet["origin"], "classifier": classifier,
                  "classifier_identity": identity, "names": names, "values": vector.tolist(), "classification_ids": sorted(used), "missing_article_ids": missing,
                  "rejected_classification_ids": rejected,
                  "event_clusters": [{"representative_id": group[0]["id"], "article_ids": sorted(a["id"] for a in group)} for group in clusters],
                  "eligible": bool(packet["article_ids"]) and not missing, "coverage_state": packet["coverage_state"],
                  "definitions": {k: "Weighted unique-event sum in the configured past evidence window" for k in names},
                  "missingness_note": "No articles has unknown coverage and is not a neutral/no-news observation; complete extraction required"}
        record["definitions"].update(coverage_observed="1 if any eligible article version observed, not a continuity guarantee", missing_classification_fraction="Missing/unsupported classifications / eligible article versions", event_count="Relevance-weighted exact URL/content/headline or attested-event clusters; semantic syndication coverage not established", novelty_unknown="1 if articles present but no time-valid earlier-event context supplied; not a novelty estimate")
        return self.records.put("features", record)
