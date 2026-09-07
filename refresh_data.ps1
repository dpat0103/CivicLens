# refresh_data.ps1
#
# Re-runs the live ingestion jobs (Census + BLS) to pull the latest
# published data into the database, then rebuilds the assistant's
# retrieval index. This is NOT part of normal startup -- run it
# manually, occasionally (e.g. once a year when Census/BLS publish new
# annual estimates, or whenever you add a new ingestion job).
#
# Requires backend\.env to have CENSUS_API_KEY and BLS_API_KEY set.
#
# Usage: from the civiclens root folder, run:
#   .\refresh_data.ps1

$root = $PSScriptRoot

# Stop on the first failed step. The steps below are order-dependent:
# fetch_census matches against Location rows that seed_locations creates,
# and fetch_bls_batch groups by the county seed_locations populates. If an
# early step fails and the script keeps going, later steps "succeed" while
# writing nothing, which looks like a clean run and isn't.
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param([string]$Label, [scriptblock]$Action)

    Write-Host ""
    Write-Host "--- $Label ---" -ForegroundColor Yellow
    & $Action
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "FAILED: $Label (exit code $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "Stopping. Later steps depend on this one." -ForegroundColor Red
        exit 1
    }
}

Write-Host "Refreshing CivicLens data from live government APIs..." -ForegroundColor Cyan
Write-Host "(This does NOT run on every startup -- only when you run this script.)" -ForegroundColor DarkGray

Set-Location "$root\backend"
.\.venv\Scripts\Activate.ps1

# 1. Create/refresh Location rows for every NJ municipality.
#    Must run first: fetch_census matches incoming Census rows against
#    existing Location rows by name and cannot create new ones itself,
#    so without this the refresh only ever touches the original pilot towns.
#    --min-population filters out tiny Census Designated Places whose data
#    is too sparse to produce a useful fact card.
Invoke-Step "Census geography (municipality list, FIPS codes, counties)" {
    python -m ingestion.seed_locations --year 2023 --min-population 500
}

# 2. ACS: population, median household income, median rent, commute.
Invoke-Step "Census ACS (population, income, rent, commute)" {
    python -m ingestion.fetch_census --year 2023 --state 34
}

# 3. LAUS: employment and unemployment, fetched once per county rather
#    than once per municipality. 21 counties x 2 measures = 42 series in
#    one batched request, versus 1000+ calls the per-town way, which would
#    blow past the BLS 500/day registered limit.
Invoke-Step "BLS LAUS (county employment, unemployment)" {
    python -m ingestion.fetch_bls_batch --start-year 2019 --end-year 2023
}

# 4. Rebuild the assistant's retrieval index.
#    Fact cards are generated from the metrics table, so skipping this
#    leaves the assistant answering from the previous refresh's numbers.
#    It fails silently in the sense that nothing errors -- the answers are
#    just quietly stale.
Invoke-Step "Rebuild assistant retrieval index" {
    python -m ingestion.build_index
}

Write-Host ""
Write-Host "Verifying data provenance..." -ForegroundColor Cyan
python -c "from app.database import SessionLocal; from app import models; from sqlalchemy import func; db = SessionLocal(); rows = db.query(models.Metric.provenance, func.count()).group_by(models.Metric.provenance).all(); print('  ' + ', '.join(f'{p}: {c}' for p, c in rows)); db.close()"

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "Crime, housing permits, and transit have no live source wired in" -ForegroundColor DarkGray
Write-Host "and will remain 'simulated' until one is added." -ForegroundColor DarkGray
Write-Host ""
Write-Host "Restart the backend (or it'll auto-reload if already running)" -ForegroundColor Green
Write-Host "to serve the refreshed data." -ForegroundColor Green