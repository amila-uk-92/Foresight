"""API endpoint integration tests."""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"

def test_inventory_endpoint():
    response = client.get("/api/datasets")
    assert response.status_code == 200
    data = response.json()
    assert "datasets" in data
    symbols = [d["symbol"] for d in data["datasets"]]
    assert "BTCUSDT" in symbols
    assert "ETHUSDT" in symbols

def test_metadata_endpoint():
    response = client.get("/api/datasets/BTCUSDT/metadata")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["source"] == "Binance Spot"
    assert data["interval"] == "1 hour (1h)"
    assert data["splits"]["training"]["duration_months"] == 36
    assert data["splits"]["validation"]["duration_months"] == 8
    assert data["splits"]["final_test"]["duration_months"] == 4

def test_candles_endpoint():
    response = client.get("/api/datasets/BTCUSDT/candles")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert isinstance(data["candles"], list)
    assert data["total"] > 0

def test_candles_filter_by_split():
    response = client.get("/api/datasets/BTCUSDT/candles?split=training")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    # Every returned candle must have split == 'training'
    assert all(c["split"] == "training" for c in data["candles"][:20])

def test_table_pagination_and_split_filter():
    response = client.get("/api/datasets/BTCUSDT/table?page=1&page_size=10&split=training")
    assert response.status_code == 200
    data = response.json()
    assert data["total_rows"] > 0
    assert len(data["rows"]) == 10
    row0 = data["rows"][0]
    assert "open" in row0
    assert "high" in row0
    assert "low" in row0
    assert "close" in row0
    assert "volume" in row0
    assert "quote_volume" in row0
    assert row0["split"] == "training"

def test_quality_report_endpoint():
    response = client.get("/api/datasets/BTCUSDT/quality")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert "missing_hours_count" in data
    assert "issues" in data

def test_manifest_endpoint():
    response = client.get("/api/datasets/BTCUSDT/manifest")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["total_files"] == 48
    assert data["verified_files"] == 48

def test_csv_export_endpoint():
    response = client.get("/api/datasets/BTCUSDT/export?split=final_test")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    lines = response.text.strip().split("\n")
    assert len(lines) > 1 # Header + rows
    header = lines[0]
    assert "open_time" in header
    assert "close" in header
    assert "split" in header


def test_comparison_rejects_unknown_family_before_starting_a_job():
    response = client.post("/api/forecasting/comparisons", json={"families": ["prophet"]})
    assert response.status_code == 409
    assert "Unknown model family" in response.json()["detail"]
