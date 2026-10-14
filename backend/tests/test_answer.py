"""The guarantee the project is built around: numeric questions never reach
a language model. Each numeric path is exercised with a model that raises
if it is called at all."""

import pytest

from app.rag.answer import answer_question
from app.rag.llm import ExtractiveLLM


class ExplodingLLM:
    name = "exploding"

    def generate(self, system, user):
        raise AssertionError("the model was reached on a numeric lookup")


def test_lookup_never_invokes_the_model(db):
    class ExplodingLLM:
        def generate(self, system, user):
            raise AssertionError("the model was reached on a numeric lookup")

    result = answer_question(db, "What is the median rent in Montclair?", llm=ExplodingLLM())
    assert result["intent"] == "lookup"
    assert result["retrieval"]["used"] is False


def test_lookup_reads_the_latest_value_from_sql(db):
    result = answer_question(db, "What is the median rent in Montclair?", llm=ExplodingLLM())
    assert "Median Rent in Montclair was $2,041 in 2023" in result["answer"]
    assert result["citations"][0]["chunk_id"] == "sql:3401347500:median_rent"
    assert result["citations"][0]["kind"] == "direct_query"
    assert result["provenance"] == "measured"
    assert result["grounded"] is True


def test_compare_never_invokes_the_model(db):
    result = answer_question(db, "Compare Princeton and Trenton", llm=ExplodingLLM())
    assert result["intent"] == "compare"
    assert result["retrieval"]["used"] is False
    assert [p["name"] for p in result["resolved_places"]] == ["Princeton", "Trenton"]


def test_compare_reports_coverage_with_each_score(db):
    result = answer_question(db, "Compare Hoboken and Bayonne", llm=ExplodingLLM())
    assert "computed from 6 of 6 scored metrics" in result["answer"]


def test_place_name_containing_a_metric_word_is_not_a_metric(db):
    # "Trenton" contains "rent". Without stripping place names first this
    # comparison would be narrowed to median rent.
    result = answer_question(db, "Compare Princeton and Trenton", llm=ExplodingLLM())
    assert result["citations"][0]["metric_keys"] == ["population", "median_rent", "median_household_income"]


def test_explanatory_question_uses_retrieval(db):
    result = answer_question(db, "Why is the growth score what it is in Camden?", llm=ExtractiveLLM())
    assert result["intent"] == "explanatory"
    assert result["retrieval"]["used"] is True
    assert result["retrieval"]["generator"] == "extractive"
    assert any(c["fips"] == "3400710000" for c in result["citations"])


def test_methodology_question_without_a_place_uses_only_methodology_docs(db):
    result = answer_question(db, "How is the Growth Score calculated?", llm=ExtractiveLLM())
    assert result["intent"] == "methodology"
    assert result["retrieval"]["chunks"]
    assert all(c.startswith("meth:") for c in result["retrieval"]["chunks"])
    assert result["provenance"] == "n/a"


def test_question_about_an_untracked_topic_is_refused_with_suggestions(db):
    result = answer_question(db, "Who is the mayor of Newark?", llm=ExplodingLLM())
    assert result["intent"] == "unsupported"
    assert result["grounded"] is False
    assert "Newark is in the dataset" in result["answer"]
    assert result["suggestions"]


def test_question_naming_nothing_known_is_refused(db):
    result = answer_question(db, "What is the capital of France?", llm=ExplodingLLM())
    assert result["intent"] == "unsupported"
    assert result["suggestions"]


@pytest.mark.parametrize("question", ["", "   "])
def test_empty_question_is_refused(db, question):
    result = answer_question(db, question, llm=ExplodingLLM())
    assert result["intent"] == "unsupported"
    assert result["answer"] == "Enter a question to get started."
