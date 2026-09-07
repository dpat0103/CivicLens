"""
Data integrity audit.

Read-only. Scans the metrics table for the failure modes that do not raise
exceptions and therefore survive a clean ingestion run:

  1. Values outside a plausible range for their unit (a commute of 15,000
     "minutes", a median rent of $4)
  2. Metrics whose value is identical across every municipality in a county
     (correct for countywide BLS data, a red flag anywhere else)
  3. Simulated rows sitting at a LATER period than real rows for the same
     metric, which makes the "latest" value fabricated and every trend wrong
  4. Series that mix measured and simulated observations
  5. Metrics missing entirely for large numbers of municipalities

Usage:
    python -m ingestion.audit_data
    python -m ingestion.audit_data --verbose
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app import models

# Plausible ranges. Deliberately wide -- these are absurdity checks, not
# statistical outlier detection.
#
# Two of these were wrong on the first real run and produced 141 false
# positives, which is worth more than the bugs they were meant to catch:
# a checker that flags correct data teaches you to ignore it.
#
#   employment ceiling was 500,000, sized for a municipality. But employment
#   is COUNTYWIDE by design, and Bergen County alone has ~505,000 employed.
#   Countywide metrics need county-scale bounds.
#
#   population floor was 1. Walpack Township, Sussex County, genuinely
#   reports ~0 residents -- it was almost entirely depopulated by the Tocks
#   Island Dam project in the 1960s and never repopulated. Real data.
PLAUSIBLE = {
    "population": (0, 400_000, "people"),
    "median_household_income": (10_000, 350_000, "$"),
    "median_rent": (300, 5_000, "$/month"),
    "avg_commute_minutes": (5, 90, "minutes"),
    "unemployment_rate": (0.5, 25, "%"),
    # Countywide, so bounded by NJ's largest county workforce, not a town's.
    "employment": (1, 800_000, "people"),
    "property_crime_rate": (0, 100, "per 1,000"),
    "violent_crime_rate": (0, 50, "per 1,000"),
    "new_housing_permits": (0, 5_000, "count"),
    "transit_ridership_index": (0, 500, "index"),
}

# Metrics reported at county level and copied to every municipality in that
# county. Uniformity across a county is correct for these and a red flag
# for anything else.
COUNTYWIDE_METRICS = {"employment", "unemployment_rate"}


def check_implausible(db, verbose):
    print("=" * 72)
    print("1. VALUES OUTSIDE PLAUSIBLE RANGE")
    print("=" * 72)

    problems = defaultdict(list)
    for metric_key, (low, high, unit) in PLAUSIBLE.items():
        rows = (
            db.query(models.Metric, models.Location)
            .join(models.Location)
            .filter(models.Metric.metric_key == metric_key)
            .all()
        )
        for metric, location in rows:
            if metric.value < low or metric.value > high:
                problems[metric_key].append((location.name, metric.period, metric.value, unit))

    if not problems:
        print("  None. All values within plausible ranges.\n")
        return 0

    for metric_key, items in sorted(problems.items()):
        low, high, unit = PLAUSIBLE[metric_key]
        print(f"\n  {metric_key}: {len(items)} values outside {low}-{high} {unit}")
        for name, period, value, unit in sorted(items)[: (999 if verbose else 5)]:
            print(f"      {name} ({period}): {value:,.1f} {unit}")
        if not verbose and len(items) > 5:
            print(f"      ...and {len(items) - 5} more")
    print()
    return sum(len(v) for v in problems.values())


def check_county_uniform(db, verbose):
    print("=" * 72)
    print("2. METRICS IDENTICAL ACROSS A WHOLE COUNTY")
    print("=" * 72)
    print("  (Expected for BLS employment data. A problem anywhere else.)\n")

    flagged = []
    metric_keys = [r[0] for r in db.query(models.Metric.metric_key).distinct()]

    for metric_key in sorted(metric_keys):
        rows = (
            db.query(models.Location.county, models.Metric.period,
                     func.count(func.distinct(models.Metric.value)).label("distinct_values"),
                     func.count(models.Metric.id).label("total"))
            .join(models.Metric, models.Metric.location_id == models.Location.id)
            .filter(models.Metric.metric_key == metric_key)
            .group_by(models.Location.county, models.Metric.period)
            .all()
        )
        uniform = [r for r in rows if r.total > 3 and r.distinct_values == 1]
        if uniform:
            flagged.append((metric_key, len(uniform), len(rows)))

    if not flagged:
        print("  None.\n")
        return

    for metric_key, uniform_count, total_groups in flagged:
        marker = "expected" if metric_key in ("employment", "unemployment_rate") else "*** CHECK ***"
        print(f"  {metric_key}: uniform in {uniform_count}/{total_groups} county-years  [{marker}]")
    print()


def check_simulated_after_real(db, verbose):
    print("=" * 72)
    print("3. SIMULATED ROWS SITTING AFTER REAL DATA")
    print("=" * 72)
    print("  These make the latest value fabricated and every trend wrong.\n")

    latest_measured = (
        db.query(models.Metric.location_id, models.Metric.metric_key,
                 func.max(models.Metric.period).label("last_real"))
        .filter(models.Metric.provenance == "measured")
        .group_by(models.Metric.location_id, models.Metric.metric_key)
        .all()
    )
    lookup = {(r.location_id, r.metric_key): r.last_real for r in latest_measured}

    offenders = []
    sim_rows = (
        db.query(models.Metric, models.Location)
        .join(models.Location)
        .filter(models.Metric.provenance == "simulated")
        .all()
    )
    for metric, location in sim_rows:
        last_real = lookup.get((metric.location_id, metric.metric_key))
        if last_real is not None and metric.period > last_real:
            offenders.append((location.name, metric.metric_key, metric.period, last_real))

    if not offenders:
        print("  None.\n")
        return 0

    print(f"  {len(offenders)} simulated observations postdate real data for the same metric.\n")
    by_metric = defaultdict(list)
    for name, key, period, last_real in offenders:
        by_metric[key].append((name, period, last_real))
    for key, items in sorted(by_metric.items()):
        periods = sorted({p for _, p, _ in items})
        last_real = items[0][2]
        print(f"    {key}: {len(items)} rows in {periods}, real data ends {last_real}")
    print()
    return len(offenders)


def check_mixed_series(db, verbose):
    print("=" * 72)
    print("4. SERIES MIXING MEASURED AND SIMULATED")
    print("=" * 72)

    rows = (
        db.query(models.Location.name, models.Metric.metric_key,
                 func.count(func.distinct(models.Metric.provenance)).label("kinds"))
        .join(models.Metric, models.Metric.location_id == models.Location.id)
        .group_by(models.Location.id, models.Metric.metric_key)
        .having(func.count(func.distinct(models.Metric.provenance)) > 1)
        .all()
    )

    if not rows:
        print("  None.\n")
        return

    print(f"  {len(rows)} (municipality, metric) series contain both.\n")
    by_metric = defaultdict(int)
    for name, key, _ in rows:
        by_metric[key] += 1
    for key, count in sorted(by_metric.items(), key=lambda kv: -kv[1]):
        print(f"    {key}: {count} municipalities")
    print()


def check_single_year_metrics(db, verbose):
    """A metric with only one period cannot produce a percent change, so it
    contributes nothing to the Growth Score. If enough metrics are
    single-year, the score collapses onto whatever is left -- and if what's
    left is countywide, every municipality in a county scores identically."""
    print("=" * 72)
    print("6. METRICS WITH ONLY ONE YEAR OF DATA")
    print("=" * 72)
    print("  One period means no percent change, so these drop out of the")
    print("  Growth Score entirely.\n")

    rows = (
        db.query(models.Metric.metric_key,
                 models.Metric.location_id,
                 func.count(func.distinct(models.Metric.period)).label("years"))
        .group_by(models.Metric.metric_key, models.Metric.location_id)
        .all()
    )
    single = defaultdict(int)
    total = defaultdict(int)
    for r in rows:
        total[r.metric_key] += 1
        if r.years < 2:
            single[r.metric_key] += 1

    # How many distinct periods each metric spans across the whole dataset.
    # This is what separates the two very different causes of a single-year
    # series, which the first version of this check conflated:
    #
    #   metric spans one year everywhere  -> only one vintage was ingested,
    #                                        a real ingestion gap to fix
    #   metric spans many years globally  -> ACS suppressed the estimate for
    #                                        this particular municipality,
    #                                        which is expected for small
    #                                        populations and not fixable by
    #                                        fetching more data
    global_years = dict(
        db.query(models.Metric.metric_key,
                 func.count(func.distinct(models.Metric.period)))
        .group_by(models.Metric.metric_key).all()
    )

    ingestion_gaps, suppression = 0, 0
    flagged = False
    for metric_key in sorted(total):
        n_single, n_total = single.get(metric_key, 0), total[metric_key]
        if n_single == 0:
            continue
        flagged = True
        pct = 100 * n_single / n_total
        spans = global_years.get(metric_key, 0)
        if spans < 2:
            cause = "*** only one vintage ingested ***"
            ingestion_gaps += n_single
        else:
            cause = f"ACS suppression (metric spans {spans} years elsewhere)"
            suppression += n_single
        print(f"    {metric_key:28} {n_single:4}/{n_total} ({pct:5.1f}%)  {cause}")

    if not flagged:
        print("  None. Every metric has at least two periods everywhere.\n")
    else:
        print()
        if suppression:
            print(f"  {suppression} are ACS suppressing estimates for small")
            print("  municipalities. Expected, not fixable, and already handled:")
            print("  those metrics drop out of the score and metric coverage")
            print("  reports the reduced count.")
        if ingestion_gaps:
            print(f"\n  {ingestion_gaps} are a real ingestion gap. Fetch more vintages:")
            print("    python -m ingestion.fetch_census --start-year 2019 --end-year 2023")
        print()
    return ingestion_gaps


def check_coverage(db, verbose):
    print("=" * 72)
    print("5. METRIC COVERAGE ACROSS MUNICIPALITIES")
    print("=" * 72)

    total_locations = db.query(models.Location).count()
    rows = (
        db.query(models.Metric.metric_key,
                 func.count(func.distinct(models.Metric.location_id)).label("locations"),
                 func.min(models.Metric.period).label("first"),
                 func.max(models.Metric.period).label("last"))
        .group_by(models.Metric.metric_key)
        .all()
    )

    print(f"  {total_locations} municipalities total\n")
    for r in sorted(rows, key=lambda x: -x.locations):
        pct = 100 * r.locations / total_locations if total_locations else 0
        flag = "" if pct > 90 else "  <-- sparse"
        print(f"    {r.metric_key:28} {r.locations:4}/{total_locations} "
              f"({pct:5.1f}%)  {r.first}-{r.last}{flag}")
    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="list every offending row")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        print()
        implausible = check_implausible(db, args.verbose)
        check_county_uniform(db, args.verbose)
        stale = check_simulated_after_real(db, args.verbose)
        check_mixed_series(db, args.verbose)
        check_coverage(db, args.verbose)
        single_year = check_single_year_metrics(db, args.verbose)

        print("=" * 72)
        print("SUMMARY")
        print("=" * 72)
        print(f"  Implausible values:            {implausible}")
        print(f"  Simulated rows after real:     {stale}")
        print(f"  Single-year from ingestion gap: {single_year}")
        if implausible or stale:
            print("\n  Run `python -m ingestion.repair_data` to fix.")
        if single_year:
            print("  Fetch more ACS vintages:")
            print("    python -m ingestion.fetch_census --start-year 2019 --end-year 2023")
        if not (implausible or stale or single_year):
            print("\n  No integrity problems found.")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    main()