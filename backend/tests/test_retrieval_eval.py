"""Labelled retrieval eval.

Unit tests prove the pipeline runs. This proves it retrieves the right
thing. Relevance regresses silently -- nothing throws when answers quietly
get worse -- so each question names the chunk that must be among those
retrieved, and the suite fails if recall drops below the floor.

Everything runs on the offline hashing embedder, which matches characters
and words, not meaning. The two xfail cases at the bottom need semantic
matching it cannot do. They are kept rather than deleted because they are
the cases that should start passing when a hosted embedding provider is
configured, which is how to verify that upgrade bought something.
"""

import pytest

from app.rag.answer import MIN_RETRIEVAL_SCORE, answer_question
from app.rag.llm import ExtractiveLLM

RECALL_FLOOR = 0.9

# (question, chunk id that must be retrieved)
EVAL_SET = [
    # Overviews of one place: the FIPS filter must hold.
    ("Tell me about housing in Montclair", "fact:3401347500:housing"),
    ("Tell me about housing in Union City", "fact:3401774630:housing"),
    ("Tell me about housing in Washington Township (Warren County)", "fact:3404177240:housing"),
    ("Tell me about real estate in Bayonne", "fact:3401703580:housing"),
    ("What is happening with housing in Camden?", "fact:3400710000:housing"),
    ("Tell me about transportation in Hoboken", "fact:3401732250:transportation"),
    ("How is Princeton doing?", "fact:3402160900:population"),
    ("What is going on in Trenton?", "fact:3402174000:population"),
    ("Give me an overview of Bloomfield", "fact:3401306260:population"),
    ("Why are rents in Jersey City what they are?", "fact:3401736000:housing"),
    ("Explain the unemployment numbers in Camden", "fact:3400710000:employment"),
    # Why questions that need a methodology note to answer honestly.
    ("Why is the growth score what it is in Camden?", "meth:growth_score"),
    ("Why is the growth score what it is in Hoboken?", "meth:growth_score"),
    ("Why do Hoboken and Bayonne have the same employment?", "meth:bls_geography"),
    ("Why does Bloomfield have the same unemployment rate as Montclair?", "meth:bls_geography"),
    ("Why is employment reported at the county level?", "meth:bls_geography"),
    ("Why does every town in a county show identical jobs figures?", "meth:bls_geography"),
    ("Why is a municipality missing from the census geography?", "meth:census_geography"),
    ("Why do two places share the same score but different coverage?", "meth:growth_score"),
    ("Why should I not read much into a single year's change?", "meth:acs_estimates"),
    # Questions about the data itself.
    ("How is the Growth Score calculated?", "meth:growth_score"),
    ("How do you turn several indicators into one number?", "meth:growth_score"),
    ("How are percent changes computed when a year is missing?", "meth:growth_score"),
    ("Is this real data or simulated?", "meth:provenance"),
    ("What does measured versus simulated mean?", "meth:provenance"),
    ("What is the margin of error on these figures?", "meth:acs_estimates"),
]

# Nothing in the corpus addresses these, so the answer must be a refusal
# rather than the nearest chunk dressed up as an answer.
REFUSALS = [
    "Who won the Super Bowl?",
    "What is the best restaurant?",
    "Tell me a joke",
    "What is the capital of France?",
]


def retrieved(db, question):
    result = answer_question(db, question, llm=ExtractiveLLM())
    return result, result["retrieval"]["chunks"]


def test_eval_set_is_large_enough():
    assert len(EVAL_SET) >= 25


def test_recall_meets_floor(db):
    misses = [(q, want) for q, want in EVAL_SET if want not in retrieved(db, q)[1]]
    recall = 1 - len(misses) / len(EVAL_SET)
    assert recall >= RECALL_FLOOR, f"recall {recall:.2f} below {RECALL_FLOOR}; missed: {misses}"


@pytest.mark.parametrize("question, expected", [(q, w) for q, w in EVAL_SET if w.startswith("fact:")])
def test_place_scoped_questions_only_retrieve_that_place(db, question, expected):
    # The metadata filter makes a neighbouring town's card impossible, not
    # unlikely. Methodology notes have no FIPS and may appear alongside.
    fips = expected.split(":")[1]
    _, chunks = retrieved(db, question)
    assert all(c.startswith("meth:") or f":{fips}:" in c for c in chunks)


@pytest.mark.parametrize("question", REFUSALS)
def test_off_topic_questions_are_refused(db, question):
    result, chunks = retrieved(db, question)
    assert result["intent"] == "unsupported"
    assert result["grounded"] is False
    assert chunks == []


def test_relevance_floor_is_positive():
    assert 0 < MIN_RETRIEVAL_SCORE < 1


@pytest.mark.xfail(
    strict=True,
    reason="needs semantic matching: 'jobless' and 'nearby towns' share no "
    "terms with the countywide employment note",
)
def test_semantic_paraphrase_of_countywide_employment(db):
    _, chunks = retrieved(db, "Why do jobless figures match across nearby towns?")
    assert "meth:bls_geography" in chunks


@pytest.mark.xfail(
    strict=True,
    reason="needs semantic matching: 'absent from the listings' paraphrases "
    "'missing from the census geography'",
)
def test_semantic_paraphrase_of_missing_municipality(db):
    _, chunks = retrieved(db, "Why would a small borough be absent from the listings?")
    assert "meth:census_geography" in chunks
