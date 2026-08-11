"""
Analytics engine.

Two responsibilities:
1. Turn a raw time series of Metric rows into a MetricSeries with
   1/3/5-year percent changes computed.
2. Roll a location's metrics up into a single 0-100 "Growth Score".

The scoring weights below are intentionally simple and documented so
they're easy to defend/explain and easy to tune later.
"""
from collections import defaultdict
from statistics import mean

# Weight of each metric's 3-year % change in the composite Growth Score.
# Positive weight = "more of this is growth". Negative weight = "less of
# this is growth" (e.g. crime).
SCORE_WEIGHTS = {
    "population": {"weight": 0.20, "direction": 1},
    "employment": {"weight": 0.20, "direction": 1},
    "new_housing_permits": {"weight": 0.20, "direction": 1},
    "median_household_income": {"weight": 0.20, "direction": 1},
    "property_crime_rate": {"weight": 0.10, "direction": -1},
    "violent_crime_rate": {"weight": 0.10, "direction": -1},
}

# A % change beyond this magnitude is treated as "maximally" good/bad,
# so one wild outlier metric can't blow up the whole score.
SATURATION_PCT = 25.0


def _pct_change(old: float, new: float) -> float | None:
    if old in (None, 0):
        return None
    return round(((new - old) / abs(old)) * 100, 2)


def build_series(rows: list, category: str, metric_key: str, label: str,
                  unit: str | None, source: str | None) -> dict:
    """rows: list of (period, value) tuples sorted ascending by period."""
    rows = sorted(rows, key=lambda r: r[0])
    history = [{"period": p, "value": v} for p, v in rows]
    latest_period, latest_value = rows[-1]

    by_period = {p: v for p, v in rows}

    def change_over(years: int):
        target = latest_period - years
        if target in by_period:
            return _pct_change(by_period[target], latest_value)
        # fall back to earliest available point if exact year missing
        earliest_period, earliest_value = rows[0]
        if earliest_period <= target:
            return None
        return None

    return {
        "category": category,
        "metric_key": metric_key,
        "label": label,
        "unit": unit,
        "latest_value": latest_value,
        "latest_period": latest_period,
        "change_1y_pct": change_over(1),
        "change_3y_pct": change_over(3),
        "change_5y_pct": change_over(5),
        "history": history,
        "source": source,
    }


def compute_growth_score(series_by_key: dict) -> tuple[float, str]:
    """series_by_key: metric_key -> MetricSeries-shaped dict (as built above).

    Returns (score 0-100, qualitative label).
    """
    weighted_scores = []
    total_weight = 0.0

    for key, cfg in SCORE_WEIGHTS.items():
        series = series_by_key.get(key)
        if not series:
            continue
        pct = series.get("change_3y_pct")
        if pct is None:
            pct = series.get("change_1y_pct")
        if pct is None:
            continue

        direction = cfg["direction"]
        signed = pct * direction

        # squash to -1..1 range using saturation, then map to 0..100
        clamped = max(-SATURATION_PCT, min(SATURATION_PCT, signed))
        normalized_0_100 = ((clamped / SATURATION_PCT) + 1) / 2 * 100

        weighted_scores.append(normalized_0_100 * cfg["weight"])
        total_weight += cfg["weight"]

    if total_weight == 0:
        return 50.0, "Insufficient data"

    score = sum(weighted_scores) / total_weight
    score = round(score, 1)

    if score >= 75:
        label = "Strong growth"
    elif score >= 60:
        label = "Moderate growth"
    elif score >= 40:
        label = "Stable"
    elif score >= 25:
        label = "Moderate decline"
    else:
        label = "Strong decline"

    return score, label


def headline_changes(series_by_key: dict, top_n: int = 5) -> list[str]:
    """Pick the biggest 3-year moves across all metrics for the
    'Biggest changes since <year>' summary."""
    candidates = []
    for series in series_by_key.values():
        pct = series.get("change_3y_pct")
        if pct is None:
            continue
        arrow = "\u2191" if pct >= 0 else "\u2193"
        candidates.append((abs(pct), f"{series['label']} {arrow} {abs(pct)}% (3yr)"))

    candidates.sort(key=lambda c: c[0], reverse=True)
    return [text for _, text in candidates[:top_n]]
