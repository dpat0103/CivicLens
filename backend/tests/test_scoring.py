import pytest

from app.scoring import (
    SATURATION_PCT,
    SCORE_WEIGHTS,
    build_series,
    compute_growth_score,
    headline_changes,
)


def series(points, key="population", unit="count"):
    return build_series(points, "population", key, key.title(), unit, "test")


def full_set(pct_by_key):
    """A series for every scored metric, each moving by the given percent
    over exactly three years."""
    out = {}
    for key in SCORE_WEIGHTS:
        pct = pct_by_key.get(key, 0.0)
        out[key] = series([(2020, 100.0), (2023, 100.0 * (1 + pct / 100))], key=key)
    return out


class TestBuildSeries:
    def test_latest_value_and_changes(self):
        s = series([(2019, 100.0), (2020, 110.0), (2021, 120.0), (2022, 125.0), (2023, 150.0)])
        assert s["latest_value"] == 150.0
        assert s["latest_period"] == 2023
        assert s["change_1y_pct"] == 20.0
        assert s["change_3y_pct"] == 36.36
        assert s["baseline_3y_period"] == 2020
        assert s["change_5y_pct"] is None

    def test_rows_in_any_order(self):
        s = series([(2023, 150.0), (2019, 100.0), (2021, 120.0)])
        assert [p["period"] for p in s["history"]] == [2019, 2021, 2023]
        assert s["latest_value"] == 150.0

    def test_missing_baseline_falls_back_to_earlier_year_never_later(self):
        # 2020 is missing. A three-year change must use 2019, which keeps the
        # window at least three years, not 2021, which would shorten it.
        s = series([(2019, 100.0), (2021, 120.0), (2022, 125.0), (2023, 130.0)])
        assert s["baseline_3y_period"] == 2019
        assert s["change_3y_pct"] == 30.0

    def test_no_earlier_observation_means_no_change(self):
        s = series([(2022, 100.0), (2023, 110.0)])
        assert s["change_3y_pct"] is None
        assert s["baseline_3y_period"] is None

    def test_zero_baseline_is_undefined_not_zero(self):
        s = series([(2020, 0.0), (2023, 10.0)])
        assert s["change_3y_pct"] is None

    def test_negative_baseline_uses_absolute_value(self):
        s = series([(2020, -50.0), (2023, -25.0)])
        assert s["change_3y_pct"] == 50.0


class TestGrowthScore:
    def test_weights_sum_to_one(self):
        assert sum(cfg["weight"] for cfg in SCORE_WEIGHTS.values()) == pytest.approx(1.0)

    def test_no_change_anywhere_is_exactly_fifty(self):
        score, label, coverage = compute_growth_score(full_set({}))
        assert score == 50.0
        assert label == "Stable"
        assert coverage == {
            "metrics_used": 6,
            "metrics_total": 6,
            "weight_covered": 1.0,
            "missing_metrics": [],
        }

    def test_saturation_caps_every_indicator(self):
        all_up = {k: 400.0 * cfg["direction"] for k, cfg in SCORE_WEIGHTS.items()}
        score, label, _ = compute_growth_score(full_set(all_up))
        assert score == 100.0
        assert label == "Strong growth"

    def test_saturated_moves_score_the_same_as_the_cap(self):
        at_cap = {"population": SATURATION_PCT}
        beyond = {"population": SATURATION_PCT * 10}
        assert compute_growth_score(full_set(at_cap))[0] == compute_growth_score(full_set(beyond))[0]

    def test_falling_poverty_raises_the_score(self):
        better, _, _ = compute_growth_score(full_set({"poverty_rate": -10.0}))
        worse, _, _ = compute_growth_score(full_set({"poverty_rate": 10.0}))
        assert better > 50.0 > worse

    def test_missing_metric_is_reported_and_weight_renormalised(self):
        data = full_set({"population": 25.0})
        del data["employment"]
        score, _, coverage = compute_growth_score(data)
        assert coverage["metrics_used"] == 5
        assert coverage["missing_metrics"] == ["employment"]
        assert coverage["weight_covered"] == 0.85
        # population is 0.20 of the remaining 0.85, at 100 points; the rest sit at 50.
        assert score == round((100 * 0.20 + 50 * 0.65) / 0.85, 1)

    def test_present_but_unusable_metric_counts_as_missing(self):
        data = full_set({})
        data["population"] = series([(2023, 100.0)])
        _, _, coverage = compute_growth_score(data)
        assert "population" in coverage["missing_metrics"]
        assert coverage["metrics_used"] == 5

    def test_falls_back_to_one_year_change(self):
        data = full_set({})
        data["population"] = series([(2022, 100.0), (2023, 125.0)])
        score, _, coverage = compute_growth_score(data)
        assert coverage["metrics_used"] == 6
        assert score > 50.0

    def test_no_data_is_insufficient_not_a_score(self):
        score, label, coverage = compute_growth_score({})
        assert (score, label) == (50.0, "Insufficient data")
        assert coverage["metrics_used"] == 0
        assert coverage["weight_covered"] == 0

    @pytest.mark.parametrize(
        "pct, label",
        [
            (25.0, "Strong growth"),
            (7.0, "Moderate growth"),
            (0.0, "Stable"),
            (-7.0, "Moderate decline"),
            (-25.0, "Strong decline"),
        ],
    )
    def test_bands(self, pct, label):
        moves = {k: pct * cfg["direction"] for k, cfg in SCORE_WEIGHTS.items()}
        assert compute_growth_score(full_set(moves))[1] == label


def test_headline_changes_ranked_by_magnitude_either_direction():
    data = {
        "a": series([(2020, 100.0), (2023, 105.0)], key="a"),
        "b": series([(2020, 100.0), (2023, 60.0)], key="b"),
        "c": series([(2020, 100.0), (2023, 120.0)], key="c"),
        "d": series([(2023, 100.0)], key="d"),
    }
    changes = headline_changes(data, top_n=2)
    assert [c["metric_key"] for c in changes] == ["b", "c"]
    assert changes[0]["baseline_period"] == 2020
