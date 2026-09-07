"""
Repair data integrity problems left by earlier ingestion runs.

Three fixes, each independently switchable so nothing is deleted without
being asked for:

  --drop-stale-simulated
      Remove simulated observations that sit at a LATER period than real
      data for the same (municipality, metric). The seed generated 2021
      through 2025 while ACS only reaches 2023, so pilot towns ended up
      with real 2023 figures followed by two fabricated years. That makes
      latest_value fabricated and every percent change meaningless, which
      is worse than having no recent data at all.

  --drop-bad-commute
      Remove avg_commute_minutes rows outside a plausible range. The
      original mapping used B08303_001E, the TRAVEL TIME TO WORK table
      total, which is a count of commuters rather than an average duration.
      Those rows are counts mislabelled as minutes and cannot be salvaged,
      only removed and refetched.

  --relabel-countywide
      Add the "(Countywide)" suffix to BLS employment labels written before
      that label existed.

Always run the audit first:
    python -m ingestion.audit_data

Then:
    python -m ingestion.repair_data --all --dry-run
    python -m ingestion.repair_data --all
"""
import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func

from app.database import SessionLocal
from app import models

PLAUSIBLE_COMMUTE_MINUTES = (5, 90)


def drop_stale_simulated(db, dry_run: bool) -> int:
    latest_measured = (
        db.query(models.Metric.location_id, models.Metric.metric_key,
                 func.max(models.Metric.period).label("last_real"))
        .filter(models.Metric.provenance == "measured")
        .group_by(models.Metric.location_id, models.Metric.metric_key)
        .all()
    )
    lookup = {(r.location_id, r.metric_key): r.last_real for r in latest_measured}

    doomed = []
    for metric in db.query(models.Metric).filter(models.Metric.provenance == "simulated").all():
        last_real = lookup.get((metric.location_id, metric.metric_key))
        if last_real is not None and metric.period > last_real:
            doomed.append(metric)

    print(f"  Stale simulated rows postdating real data: {len(doomed)}")
    if doomed and not dry_run:
        for metric in doomed:
            db.delete(metric)
    return len(doomed)


def drop_bad_commute(db, dry_run: bool) -> int:
    low, high = PLAUSIBLE_COMMUTE_MINUTES
    doomed = (
        db.query(models.Metric)
        .filter(
            models.Metric.metric_key == "avg_commute_minutes",
            (models.Metric.value < low) | (models.Metric.value > high),
        )
        .all()
    )
    print(f"  Commute values outside {low}-{high} minutes: {len(doomed)}")
    if doomed and not dry_run:
        for metric in doomed:
            db.delete(metric)
    return len(doomed)


def relabel_countywide(db, dry_run: bool) -> int:
    updates = {
        "employment": "Employment (Countywide)",
        "unemployment_rate": "Unemployment Rate (Countywide)",
    }
    changed = 0
    for metric_key, new_label in updates.items():
        rows = (
            db.query(models.Metric)
            .filter(
                models.Metric.metric_key == metric_key,
                models.Metric.provenance == "measured",
                models.Metric.label != new_label,
            )
            .all()
        )
        changed += len(rows)
        if not dry_run:
            for metric in rows:
                metric.label = new_label
    print(f"  BLS rows needing the countywide label: {changed}")
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop-stale-simulated", action="store_true")
    parser.add_argument("--drop-bad-commute", action="store_true")
    parser.add_argument("--relabel-countywide", action="store_true")
    parser.add_argument("--all", action="store_true", help="apply all three")
    parser.add_argument("--dry-run", action="store_true", help="report without changing anything")
    args = parser.parse_args()

    do_stale = args.drop_stale_simulated or args.all
    do_commute = args.drop_bad_commute or args.all
    do_label = args.relabel_countywide or args.all

    if not any([do_stale, do_commute, do_label]):
        parser.error("Pick at least one repair, or --all.")

    mode = "DRY RUN, nothing will be changed" if args.dry_run else "APPLYING CHANGES"
    print(f"\n{mode}\n")

    db = SessionLocal()
    try:
        before = db.query(models.Metric).count()
        total = 0
        if do_stale:
            total += drop_stale_simulated(db, args.dry_run)
        if do_commute:
            total += drop_bad_commute(db, args.dry_run)
        if do_label:
            total += relabel_countywide(db, args.dry_run)

        if not args.dry_run:
            db.commit()
            after = db.query(models.Metric).count()
            print(f"\n  Metric rows: {before} -> {after}")
            rows = (
                db.query(models.Metric.provenance, func.count())
                .group_by(models.Metric.provenance).all()
            )
            print(f"  Provenance now: {dict(rows)}")
            print("\n  Rebuild the assistant index:  python -m ingestion.build_index")
        else:
            print(f"\n  {total} rows would be affected. Re-run without --dry-run to apply.")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    main()
