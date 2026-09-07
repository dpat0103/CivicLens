"""
Turns stored observations into comparable series and a composite score.

Two jobs:
  build_series          (period, value) pairs -> latest value, 1/3/5-year
                        percent change, and the baseline period each change
                        was measured from.
  compute_growth_score  a location's series -> one 0-100 figure, its band,
                        and how much of the composite actually had data.

The weights are a judgement, not a finding, so they are declared in one
place and reported through the API rather than buried in the calculation.
"""
from collections import defaultdict
from statistics import mean

# Indicators in the composite and their share of it. direction -1 marks an
# indicator where a fall is the desirable outcome.
#
# Selection rule: every indicator here has measured statewide coverage. An
# indicator missing for most municipalities drops out of the weighted average
# for those municipalities, and the score quietly collapses onto whatever
# remains, which is how a composite ends up meaning something different for
# each place. Five of the six vary by municipality; employment is countywide,
# so it contributes the same value to every municipality in a county.
SCORE_WEIGHTS = {
    "population": {"weight": 0.20, "direction": 1},
    "median_household_income": {"weight": 0.20, "direction": 1},
    "median_home_value": {"weight": 0.15, "direction": 1},
    "bachelors_or_higher_pct": {"weight": 0.15, "direction": 1},
    "poverty_rate": {"weight": 0.15, "direction": -1},
    "employment": {"weight": 0.15, "direction": 1},
}

# Percent changes are clamped to +/- this before scoring, so one indicator
# moving 400% cannot drag the whole composite to an extreme. Small
# municipalities produce those swings routinely on ACS estimates.
SATURATION_PCT = 25.0


def _pct_change(old: float, new: float) -> float | None:
    """None when the baseline is zero or missing: percent change from zero is
    undefined, and returning 0 would assert no movement rather than no basis
    for comparison."""
    if old in (None, 0):
        return None
    return round(((new - old) / abs(old)) * 100, 2)


def build_series(rows: list, category: str, metric_key: str, label: str,
                  unit: str | None, source: str | None) -> dict:
    """Build one metric's series. `rows` is (period, value) pairs, any order."""
    rows = sorted(rows, key=lambda r: r[0])
    history = [{"period": p, "value": v} for p, v in rows]
    latest_period, latest_value = rows[-1]

    by_period = {p: v for p, v in rows}

    def change_over(years: int):
        """Percent change over `years`, with a fallback for missing vintages.

        Returns (pct_change, baseline_period). ACS suppresses estimates for
        small municipalities, so the exact baseline year is often absent. The
        fallback takes the nearest observation at or before the target, never
        after: falling forward would shorten the measurement window, making a
        "three year change" silently a two year one.

        baseline_period is returned so callers can label the real window
        rather than the requested one.
        """
        target = latest_period - years
        if target in by_period:
            return _pct_change(by_period[target], latest_value), target

        # Nearest observation at or before the target year. Going earlier
        # rather than later keeps the window at least as long as requested,
        # so a 3-year change is never secretly a 2-year change.
        candidates = [p for p in by_period if p <= target]
        if not candidates:
            return None, None
        baseline_period = max(candidates)
        return _pct_change(by_period[baseline_period], latest_value), baseline_period

    change_1y, baseline_1y = change_over(1)
    change_3y, baseline_3y = change_over(3)
    change_5y, baseline_5y = change_over(5)

    return {
        "category": category,
        "metric_key": metric_key,
        "label": label,
        "unit": unit,
        "latest_value": latest_value,
        "latest_period": latest_period,
        "change_1y_pct": change_1y,
        "change_3y_pct": change_3y,
        "change_5y_pct": change_5y,
        "baseline_1y_period": baseline_1y,
        "baseline_3y_period": baseline_3y,
        "baseline_5y_period": baseline_5y,
        "history": history,
        "source": source,
    }


def compute_growth_score(series_by_key: dict) -> tuple[float, str, dict]:
    """series_by_key: metric_key -> MetricSeries-shaped dict (as built above).

    Returns (score 0-100, qualitative label, coverage).

    The score is a weighted average over only the indicators with usable
    data, renormalised by the weight that actually contributed. That handles
    gaps correctly but makes two scores non-comparable in a way the number
    itself does not reveal: 68.4 from six indicators and 68.4 from three are
    the same figure resting on different evidence. Coverage is returned
    alongside so callers can surface the difference.
    """
    weighted_scores = []
    total_weight = 0.0
    used: list[str] = []
    missing: list[str] = []

    for key, cfg in SCORE_WEIGHTS.items():
        series = series_by_key.get(key)
        if not series:
            missing.append(key)
            continue
        pct = series.get("change_3y_pct")
        if pct is None:
            pct = series.get("change_1y_pct")
        if pct is None:
            # Present but unusable: a zero baseline leaves percent change
            # undefined. Counts as missing, since it contributes nothing.
            missing.append(key)
            continue

        direction = cfg["direction"]
        signed = pct * direction

        # squash to -1..1 range using saturation, then map to 0..100
        clamped = max(-SATURATION_PCT, min(SATURATION_PCT, signed))
        normalized_0_100 = ((clamped / SATURATION_PCT) + 1) / 2 * 100

        weighted_scores.append(normalized_0_100 * cfg["weight"])
        total_weight += cfg["weight"]
        used.append(key)

    coverage = {
        "metrics_used": len(used),
        "metrics_total": len(SCORE_WEIGHTS),
        "weight_covered": round(total_weight, 3),
        "missing_metrics": missing,
    }

    if total_weight == 0:
        return 50.0, "Insufficient data", coverage

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

    return score, label, coverage


def headline_changes(series_by_key: dict, top_n: int = 5) -> list[dict]:
    """Largest three-year moves across all indicators.

    Returns structured records, not rendered strings. Whether a move is good
    news depends on the indicator -- a falling poverty rate is favourable, a
    falling population is not -- and that judgement belongs in the
    presentation layer, which already knows which indicators are inverted.
    """
    candidates = []
    for series in series_by_key.values():
        pct = series.get("change_3y_pct")
        if pct is None:
            continue
        candidates.append((abs(pct), {
            "metric_key": series["metric_key"],
            "label": series["label"],
            "change_3y_pct": pct,
            "baseline_period": series.get("baseline_3y_period"),
            "latest_period": series.get("latest_period"),
        }))

    candidates.sort(key=lambda c: c[0], reverse=True)
    return [record for _, record in candidates[:top_n]]