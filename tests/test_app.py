import os

import pytest
from flask import Flask
from prometheus_api_client import PrometheusConnect
from src.app import blueprint

# Set environment variables for testing
os.environ["PROMETHEUS_URL"] = "http://mock-prometheus-url"


@pytest.fixture
def app():
    """Fixture for creating the Flask app with the test configuration."""
    app = Flask(__name__)
    app.config["prometheus_connection"] = PrometheusConnect(
        url=os.environ["PROMETHEUS_URL"], disable_ssl=True
    )
    app.register_blueprint(blueprint)
    return app


def test_index(client):
    """Test the index endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Prometheus Metric Preview" in response.data


def test_health_success(client, requests_mock):
    """Test the health endpoint with a successful Prometheus connection."""
    # Mock Prometheus connection check
    requests_mock.get("http://mock-prometheus-url/", json={"status": "success"})

    response = client.get("/health")
    assert response.status_code == 200
    assert response.data == b"OK"


def test_health_failure(client, requests_mock):
    """Test the health endpoint with a failed Prometheus connection."""
    # Mock Prometheus connection failure
    requests_mock.get("http://mock-prometheus-url/", status_code=500)

    response = client.get("/health")
    assert response.status_code == 400
    assert b"Failed connecting to prometheus" in response.data


def test_preview_query_unauthorized(client):
    """Test the /preview endpoint with missing/invalid token."""
    response = client.get("/preview")
    assert response.status_code == 401
    assert b"Unauthorized" in response.data


def test_preview_query_validation_error(client):
    """Test the /preview endpoint with invalid input."""
    headers = {"Authorization": "preview-operator"}
    response = client.get("/preview", headers=headers)
    assert response.status_code == 400
    assert b"error" in response.data


def test_preview_query_prometheus_error(client, requests_mock):
    """Test the /preview endpoint with prometheus API error."""
    headers = {"Authorization": "preview-operator"}
    params = {"query": "up", "title": "Test Metric"}

    # Mock Prometheus query response
    requests_mock.get(
        "http://mock-prometheus-url/api/v1/query_range", json={}, status_code=400
    )

    response = client.get("/preview", headers=headers, query_string=params)
    assert response.status_code == 500
    assert response.headers["Content-Type"] == "application/json"


def test_preview_query_success(client, requests_mock):
    """Test the /preview endpoint with valid input."""
    headers = {"Authorization": "preview-operator"}
    params = {"query": "up", "title": "Test Metric"}

    # Mock Prometheus query response
    requests_mock.get(
        "http://mock-prometheus-url/api/v1/query_range",
        json={
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"container": "prometheus"},
                        "values": [
                            [1735379519, "1"],
                            [1735380119, "1"],
                            [1735380719, "1"],
                            [1735381319, "1"],
                            [1735381919, "1"],
                        ],
                    }
                ]
            },
        },
    )

    response = client.get("/preview", headers=headers, query_string=params)
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "image/png"
