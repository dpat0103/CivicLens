#!/usr/bin/env bash
# Re-run the live ingestion jobs (Census and BLS), then rebuild the
# assistant's retrieval index. Not part of normal startup: run it when
# Census or BLS publish new estimates.
#
# Requires CENSUS_API_KEY and BLS_API_KEY, in the environment or in
# backend/.env. Writes to DATABASE_URL (local SQLite if unset).
#
# Works on macOS, Linux and Git Bash on Windows. The PowerShell equivalent
# is scripts/refresh_data.ps1.
#
# Usage, from the repository root:
#   ./scripts/refresh_data.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
python="$root/backend/.venv/bin/python"
[ -x "$python" ] || python="$root/backend/.venv/Scripts/python.exe"
if [ ! -x "$python" ]; then
  echo "No virtualenv at backend/.venv. Create it first (see README, Running it)." >&2
  exit 1
fi

cd "$root/backend"

# Order matters, and set -e stops at the first failure: fetch_census
# matches the Location rows seed_locations creates, fetch_bls_batch groups
# by the county it populates, and build_index regenerates fact cards from
# the metrics table, so a later step after a failed one would "succeed"
# while writing nothing.
step() {
  echo
  echo "--- $1 ---"
  shift
  "$python" -m "$@"
}

step "Census geography (all 564 municipalities, FIPS codes, counties)" ingestion.seed_locations --year 2023
step "Census ACS (population, income, housing, education, commute)" ingestion.fetch_census --start-year 2019 --end-year 2023
step "BLS LAUS (county employment and unemployment)" ingestion.fetch_bls_batch --start-year 2019 --end-year 2023
step "Rebuild the assistant's retrieval index" ingestion.build_index
step "Integrity audit" ingestion.audit_data

echo
echo "Done. Restart the backend, or let --reload pick it up, to serve the refreshed data."
