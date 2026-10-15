"""Generated prose may only contain numbers that appear in the records it
was written from. Anything else is discarded for the extractive answer."""

import re

import pytest

from app.rag.answer import answer_question
from app.rag.llm import ExtractiveLLM
from app.rag.numeric_check import extract_numbers, ungrounded_numbers


class ExplodingLLM:
    name = "exploding"

    def generate(self, system, user):
        raise AssertionError("the model was reached on a numeric question")


class InventingLLM:
    """Writes a plausible sentence around a figure that is not in context."""

    name = "inventing"

    def generate(self, system, user):
        return "Employment is countywide, and Hudson County added 12,345 jobs last year."


class FaithfulLLM:
    """Repeats a figure from the context, formatted differently."""

    name = "faithful"

    def generate(self, system, user):
        context = user.split("CONTEXT:", 1)[1].split("QUESTION:", 1)[0]
        figure = re.search(r"\$[\d,]+", context).group()
        return f"The context reports a figure of {figure.replace(',', '').replace('$', '')} dollars."


class TestExtractNumbers:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("$2,410", {2410.0}),
            ("2410", {2410.0}),
            ("10.9%", {10.9}),
            ("in 2023, a change of +10.9%", {2023.0, 10.9}),
            ("down 4.1% from $1,250.50.", {4.1, 1250.5}),
            ("figures for 2019 through 2023", {2019.0, 2023.0}),
            ("a 5-year estimate", {5.0}),
            ("no numbers here", set()),
        ],
    )
    def test_formats(self, text, expected):
        assert extract_numbers(text) == expected

    def test_formatting_differences_are_grounded(self):
        assert ungrounded_numbers("Rent was 2410 dollars, up 10.9 percent.", "Rent $2,410, +10.9%") == []

    def test_a_rounded_figure_is_not_grounded(self):
        # Close is not the same. A model rounding $2,410 to $2,400 has
        # changed the figure.
        assert ungrounded_numbers("Rent is about $2,400.", "Rent was $2,410.") == [2400.0]


def test_invented_number_triggers_extractive_fallback(db):
    question = "Explain the unemployment numbers in Camden"
    result = answer_question(db, question, llm=InventingLLM())
    expected = answer_question(db, question, llm=ExtractiveLLM())

    assert result["numeric_check"] == "failed_fallback"
    assert "12,345" not in result["answer"]
    assert result["answer"] == expected["answer"]
    assert result["retrieval"]["generator"] == "extractive"


def test_number_repeated_from_context_passes(db):
    result = answer_question(db, "Tell me about housing in Montclair", llm=FaithfulLLM())
    assert result["numeric_check"] == "passed"
    assert result["retrieval"]["generator"] == "faithful"
    assert result["answer"].startswith("The context reports a figure of")


def test_extractive_generator_always_passes(db):
    result = answer_question(db, "Why is the growth score what it is in Camden?", llm=ExtractiveLLM())
    assert result["numeric_check"] == "passed"


def test_sql_answers_report_no_generated_numbers(db):
    result = answer_question(db, "What is the median rent in Montclair?", llm=ExplodingLLM())
    assert result["numeric_check"] == "not_applicable"


def test_should_i_comparison_is_answered_from_sql(db):
    result = answer_question(
        db, "Should I move to Montclair or Bloomfield for cheaper rent?", llm=ExplodingLLM()
    )
    assert result["intent"] == "compare"
    assert result["retrieval"]["used"] is False
    assert [p["name"] for p in result["resolved_places"]] == ["Montclair", "Bloomfield"]
    assert "Median Rent $2,041" in result["answer"]
    assert "Median Rent $1,712" in result["answer"]


def test_why_comparison_keeps_sql_figures_and_checks_the_explanation(db):
    result = answer_question(db, "Why do Hoboken and Bayonne have the same employment?", llm=InventingLLM())
    assert result["intent"] == "compare"
    # Figures from SQL first, then the checked explanation.
    assert result["answer"].startswith("Hoboken: Growth Score")
    assert result["retrieval"]["used"] is True
    assert "meth:bls_geography" in result["retrieval"]["chunks"]
    assert result["numeric_check"] == "failed_fallback"
    assert "12,345" not in result["answer"]
