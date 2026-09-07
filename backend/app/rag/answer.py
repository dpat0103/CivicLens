"""
Answer orchestration.

Flow:
    resolve places -> route intent -> answer

LOOKUP and COMPARE are served straight from SQL. EXPLANATORY and METHODOLOGY
go through FIPS-filtered retrieval into a generation model that is only ever
shown retrieved text. UNSUPPORTED refuses.

Every response carries the retrieved chunk ids, the resolved FIPS codes and
the provenance of the underlying rows, so any answer can be traced back to
the records that produced it.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from .. import models
from ..scoring import build_series, compute_growth_score
from . import store
from .corpus import _fmt
from .embeddings import get_embedder
from .llm import SYSTEM_PROMPT, get_llm
from .query_router import Intent, route
from .resolver import known_place_names, resolve_places, strip_places

# Below this cosine score the retrieved context is treated as irrelevant and
# the endpoint refuses rather than generating. Tuned against the eval set in
# tests/test_retrieval_eval.py.
MIN_RETRIEVAL_SCORE = 0.12


def _metric_rows(db: Session, fips: str, metric_key: str) -> list[models.Metric]:
    loc = db.query(models.Location).filter(models.Location.fips == fips).first()
    if not loc:
        return []
    return (
        db.query(models.Metric)
        .filter(models.Metric.location_id == loc.id, models.Metric.metric_key == metric_key)
        .order_by(models.Metric.period)
        .all()
    )


# Shown when a question falls outside the data. Concrete examples are far
# more useful than a list of every municipality held: the earlier version
# printed all 564 names, which buried the actual message and was unreadable.
SUGGESTED_QUESTIONS = [
    "What is the median rent in Montclair?",
    "Compare Princeton and Trenton",
    "Why is employment reported countywide?",
]


def _refusal(question: str, reason: str, db: Session, suggestions: list[str] | None = None) -> dict:
    return {
        "question": question,
        "intent": Intent.UNSUPPORTED.value,
        "answer": reason,
        "grounded": False,
        "citations": [],
        "resolved_places": [],
        "provenance": "n/a",
        "suggestions": suggestions or SUGGESTED_QUESTIONS,
        "retrieval": {"used": False, "chunks": []},
    }


def _provenance_note(provenances: set[str]) -> str:
    if provenances == {"simulated"}:
        return (" These figures are simulated demonstration data, not measured "
                "observations from the Census or BLS.")
    if "simulated" in provenances:
        return (" Some of the figures above are simulated demonstration data rather "
                "than measured observations.")
    return ""


def _answer_lookup(db: Session, question: str, places, metric_keys) -> dict:
    """No model touches this path. Values come from SQL and formatting only."""
    place = places[0]
    sentences, citations, provenances = [], [], set()

    for key in metric_keys:
        rows = _metric_rows(db, place.fips, key)
        if not rows:
            continue
        latest = rows[-1]
        series = build_series(
            [(r.period, r.value) for r in rows],
            latest.category, key, latest.label, latest.unit, latest.source,
        )
        sentence = (
            f"{latest.label} in {place.name} was {_fmt(latest.value, latest.unit)} "
            f"in {latest.period}"
        )
        change = series.get("change_3y_pct")
        if change is not None:
            sentence += f", a change of {change:+.1f}% over three years"
        sentences.append(sentence + ".")

        for r in rows:
            provenances.add(r.provenance or "measured")
        citations.append({
            "chunk_id": f"sql:{place.fips}:{key}",
            "kind": "direct_query",
            "fips": place.fips,
            "location_name": place.name,
            "category": latest.category,
            "metric_keys": [key],
            "periods": [r.period for r in rows],
            "sources": sorted({r.source for r in rows if r.source}),
            "source_urls": sorted({r.source_url for r in rows if r.source_url}),
            "provenance": sorted({r.provenance or "measured" for r in rows}),
            "score": None,
        })

    if not sentences:
        return _refusal(
            question,
            f"No data held for that indicator in {place.name}.",
            db,
            suggestions=[f"What is the population of {place.name}?",
                         f"What is the median rent in {place.name}?"],
        )

    answer = " ".join(sentences) + _provenance_note(provenances)
    return {
        "question": question,
        "intent": Intent.LOOKUP.value,
        "answer": answer,
        "grounded": True,
        "citations": citations,
        "resolved_places": [{"fips": place.fips, "name": place.name}],
        "provenance": "simulated" if "simulated" in provenances else "measured",
        "retrieval": {"used": False, "chunks": []},
    }


def _answer_compare(db: Session, question: str, places, metric_keys) -> dict:
    """Also model-free. Comparison is arithmetic, not language."""
    keys = metric_keys or ["population", "median_rent", "median_household_income"]
    lines, citations, provenances = [], [], set()

    for place in places:
        parts = []
        series_by_key = {}
        all_rows = (
            db.query(models.Metric)
            .join(models.Location)
            .filter(models.Location.fips == place.fips)
            .order_by(models.Metric.period)
            .all()
        )
        grouped = defaultdict(list)
        meta = {}
        for r in all_rows:
            grouped[r.metric_key].append((r.period, r.value))
            meta[r.metric_key] = r
            provenances.add(r.provenance or "measured")
        for k, pts in grouped.items():
            m = meta[k]
            series_by_key[k] = build_series(pts, m.category, k, m.label, m.unit, m.source)

        score, label, coverage = compute_growth_score(series_by_key)
        # Previously recounted by hand here against a hardcoded key list,
        # which could drift from SCORE_WEIGHTS and counted a metric as
        # covered merely for being present, even when its percent change
        # was unusable. compute_growth_score knows which metrics actually
        # contributed, so take the number from there.

        for key in keys:
            s = series_by_key.get(key)
            if s:
                parts.append(f"{s['label']} {_fmt(s['latest_value'], s['unit'])}")
        lines.append(
            f"{place.name}: Growth Score {score} ({label}, computed from "
            f"{coverage['metrics_used']} of {coverage['metrics_total']} "
            f"scored metrics). " + ", ".join(parts) + "."
        )
        citations.append({
            "chunk_id": f"sql:{place.fips}:compare",
            "kind": "direct_query",
            "fips": place.fips,
            "location_name": place.name,
            "category": None,
            "metric_keys": keys,
            "periods": sorted({p for pts in grouped.values() for p, _ in pts}),
            "sources": sorted({r.source for r in all_rows if r.source}),
            "source_urls": sorted({r.source_url for r in all_rows if r.source_url}),
            "provenance": sorted({r.provenance or "measured" for r in all_rows}),
            "score": None,
        })

    return {
        "question": question,
        "intent": Intent.COMPARE.value,
        "answer": " ".join(lines) + _provenance_note(provenances),
        "grounded": True,
        "citations": citations,
        "resolved_places": [{"fips": p.fips, "name": p.name} for p in places],
        "provenance": "simulated" if "simulated" in provenances else "measured",
        "retrieval": {"used": False, "chunks": []},
    }


def _retrieve(db, question, places, intent, embedder, categories=None):
    """Retrieve with guaranteed coverage of every named place.

    A single global top-k fails on comparative questions. Asking why Camden
    scores below Jersey City pulls the scoring methodology document for both
    slots and crowds out the municipal fact cards entirely, so the answer ends
    up explaining how scoring works without ever mentioning either place.

    So slots are reserved per place: each named municipality contributes its
    own best chunks, and the remainder is filled from the unfiltered pool for
    the general context (methodology, definitions, caveats).
    """
    query_vec = embedder.embed([question])[0]

    # A methodology question with no place named should not pull municipal
    # fact cards at all. They add noise and drag simulated provenance onto an
    # answer that is purely about how the system works.
    if intent is Intent.METHODOLOGY and not places:
        return store.search(db, query_vec, top_k=3, kinds=["methodology"],
                            query_text=question)

    if not places:
        return store.search(db, query_vec, top_k=4, query_text=question)

    hits, seen = [], set()
    # Fewer, better chunks. Six fact cards produced answers nobody finished
    # reading, and the extra context did not improve them.
    per_place = 2 if len(places) > 1 else 3
    for place in places:
        for hit in store.search(db, query_vec, top_k=per_place,
                                fips_filter=[place.fips], kinds=["fact_card"],
                                query_text=question):
            if hit.row.chunk_id not in seen:
                seen.add(hit.row.chunk_id)
                hits.append(hit)

    # Methodology only for questions that actually ask for a reason. An
    # overview request ("tell me about housing in Montclair") wants figures,
    # and a methodology chunk just adds a sentence about Census geography
    # that has nothing to do with the answer.
    asks_why = question.lower().strip().startswith(("why", "how come")) or \
        any(w in question.lower() for w in ("explain", "reason", "because"))
    if asks_why:
        for hit in store.search(db, query_vec, top_k=1, kinds=["methodology"],
                                query_text=question):
            if hit.row.chunk_id not in seen:
                seen.add(hit.row.chunk_id)
                hits.append(hit)

    if categories:
        # "Tell me about housing" should not answer with employment figures.
        wanted = set(categories)
        filtered = [h for h in hits
                    if h.row.kind != "fact_card" or h.row.category in wanted]
        if any(h.row.kind == "fact_card" for h in filtered):
            hits = filtered

    return sorted(hits, key=lambda h: h.score, reverse=True)


def _answer_via_retrieval(db, question, places, intent, embedder, llm, categories=None) -> dict:
    fips_filter = [p.fips for p in places]
    hits = _retrieve(db, question, places, intent, embedder, categories)

    if not hits:
        return _refusal(question, "Nothing relevant found in the indexed data.", db)

    # The floor is checked against the single best hit, not applied to every
    # chunk. Fact cards and methodology documents have very different score
    # distributions -- cards are mostly numbers and labels, documents are
    # prose -- so one global cutoff prunes every card and leaves an answer
    # that explains the methodology without ever mentioning the place asked
    # about. The floor's job is to catch questions nothing in the corpus
    # addresses, and the best hit is the right signal for that.
    if max(h.score for h in hits) < MIN_RETRIEVAL_SCORE:
        return _refusal(question, "Nothing relevant found in the indexed data.", db)

    # Place-scoped chunks were selected by an explicit FIPS filter, so their
    # topical relevance is established by metadata rather than by cosine
    # score. Keep them. Prune only unfiltered chunks that fall below the floor.
    hits = [h for h in hits if h.row.fips in fips_filter or h.score >= MIN_RETRIEVAL_SCORE]

    # If the question named a place, at least one hit must actually be about
    # that place. Methodology docs alone are not grounds to answer a
    # place-specific question.
    if places and not any(h.row.fips in fips_filter for h in hits):
        return _refusal(
            question,
            f"No indexed records for {places[0].name} cover that topic.",
            db,
            suggestions=[f"Tell me about housing in {places[0].name}",
                         f"What is the population of {places[0].name}?"],
        )

    ordered = hits
    if intent is Intent.EXPLANATORY:
        # Put methodology ahead of municipal figures. A "why" question wants
        # the reason first; the numbers are supporting detail. Ranked purely
        # by relevance the fact cards win on term overlap and the answer
        # ends up restating the observation instead of explaining it.
        ordered = [h for h in hits if h.row.kind == "methodology"] + \
                  [h for h in hits if h.row.kind != "methodology"]

    context = "\n---\n".join(h.row.text for h in ordered)
    user = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
    answer = llm.generate(SYSTEM_PROMPT, user)

    provenances = {h.row.provenance for h in hits} - {"n/a"}
    if "simulated" in provenances and "simulated" not in answer.lower():
        answer += _provenance_note(provenances)

    if not provenances:
        # Every chunk was a methodology document, so no observation underlies
        # this answer and claiming "measured" would overstate it.
        resolved_provenance = "n/a"
    elif "simulated" in provenances:
        resolved_provenance = "simulated"
    else:
        resolved_provenance = "measured"

    return {
        "question": question,
        "intent": intent.value,
        "answer": answer,
        "grounded": True,
        "citations": [h.as_citation() for h in hits],
        "resolved_places": [{"fips": p.fips, "name": p.name} for p in places],
        "provenance": resolved_provenance,
        "retrieval": {
            "used": True,
            "chunks": [h.row.chunk_id for h in hits],
            "top_score": round(hits[0].score, 4),
            "generator": llm.name,
        },
    }


def answer_question(db: Session, question: str, embedder=None, llm=None) -> dict:
    question = (question or "").strip()
    if not question:
        return _refusal("", "Enter a question to get started.", db)

    embedder = embedder or get_embedder()
    llm = llm or get_llm()

    places = resolve_places(db, question)
    # Route on text with place names removed, so municipality names cannot
    # be mistaken for metric keywords.
    routed = route(strip_places(question, places), len(places))

    if routed.intent is Intent.LOOKUP:
        return _answer_lookup(db, question, places, routed.metric_keys)
    if routed.intent is Intent.COMPARE:
        return _answer_compare(db, question, places, routed.metric_keys)
    if routed.intent in (Intent.EXPLANATORY, Intent.METHODOLOGY):
        return _answer_via_retrieval(db, question, places, routed.intent,
                                     embedder, llm, routed.categories)
    if places:
        return _refusal(
            question,
            f"{places[0].name} is in the dataset, but that question is not about "
            f"an indicator CivicLens tracks.",
            db,
            suggestions=[f"What is the median rent in {places[0].name}?",
                         f"Why is the growth score what it is in {places[0].name}?"],
        )
    return _refusal(
        question,
        "That question is outside the CivicLens dataset, which covers housing, "
        "income, employment, education and commuting in New Jersey.",
        db,
    )