"""HTTP layer. Thin by design, so these check transport concerns and the
response shapes the frontend's hand-maintained types in lib/api.ts rely on."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


@pytest.fixture
def client_for():
    def make(session):
        app.dependency_overrides[get_db] = lambda: session
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


@pytest.fixture
def client(client_for, db):
    return client_for(db)


def test_ping_needs_no_database(client):
    assert client.get("/ping").json() == {"status": "ok"}


def test_health_reports_database(client):
    body = client.get("/").json()
    assert body["service"] == "civiclens-api"
    assert body["status"] in ("ok", "degraded")


def test_list_and_search_locations(client):
    everything = client.get("/locations").json()
    assert len(everything) == 15
    assert [loc["name"] for loc in everything] == sorted(loc["name"] for loc in everything)

    found = client.get("/locations", params={"q": "hob"}).json()
    assert [loc["name"] for loc in found] == ["Hoboken"]
    assert set(found[0]) == {
        "id",
        "fips",
        "name",
        "state",
        "county",
        "location_type",
        "latitude",
        "longitude",
    }


def test_report_shape(client):
    report = client.get("/locations/3401732250/report").json()
    assert report["location"]["name"] == "Hoboken"
    assert report["metric_coverage"]["metrics_used"] == 6
    assert set(report["categories"]) == {"population", "housing", "employment", "transportation"}
    rent = next(s for s in report["categories"]["housing"] if s["metric_key"] == "median_rent")
    assert rent["latest_value"] == 2689
    assert rent["latest_period"] == 2023
    assert len(rent["history"]) == 5
    assert report["headline_changes"]


def test_report_unknown_fips_is_404(client):
    assert client.get("/locations/0000000000/report").status_code == 404


def test_compare(client):
    body = client.get("/compare", params={"fips": ["3401732250", "3401703580"]}).json()
    assert [row["location"]["name"] for row in body["rows"]] == ["Hoboken", "Bayonne"]
    # Employment is countywide, so two Hudson County towns share it.
    assert body["rows"][0]["metrics"]["employment"] == body["rows"][1]["metrics"]["employment"]


@pytest.mark.parametrize(
    "codes, status",
    [
        (["3401732250"], 400),
        (["3401732250"] * 7, 400),
        (["3401732250", "0000000000"], 404),
    ],
)
def test_compare_rejects_bad_requests(client, codes, status):
    assert client.get("/compare", params={"fips": codes}).status_code == status


def test_ask(client):
    body = client.post("/ask", json={"question": "What is the median rent in Hoboken?"}).json()
    assert body["intent"] == "lookup"
    assert "$2,689" in body["answer"]


def test_ask_without_an_index_is_503(client_for, empty_db):
    response = client_for(empty_db).post("/ask", json={"question": "anything"})
    assert response.status_code == 503
    assert "build_index" in response.json()["detail"]


def test_corpus_stats(client):
    stats = client.get("/ask/corpus").json()
    assert stats["by_kind"]["methodology"] == 6
    assert stats["by_kind"]["fact_card"] == 15 * 4
    assert stats["embedding_provider"] == ["HashingEmbedder"]
