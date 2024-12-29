import gc
import io
import os
import sys
import logging
from datetime import datetime, timedelta, timezone

from cerberus import Validator
from flask import current_app, Blueprint, Flask, jsonify, Response, request
from prometheus_api_client import PrometheusConnect
from prometheus_api_client.exceptions import PrometheusApiClientException
import matplotlib.pyplot as plt
from waitress import serve

logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

PREVIEW_REQUEST_SCHEMA = {
    "query": {"type": "string", "required": True},
    "title": {"type": "string"},
}

VALID_TOKEN = os.environ.get("PREVIEW_ACCESS_TOKEN", "preview-operator")

blueprint = Blueprint("prometheus_metric_preview", __name__)


def token_required(f):
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token or token != VALID_TOKEN:
            return jsonify({"body": "Unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapper


@blueprint.route("/")
def index():
    return """
<!doctype html>
<html lang="en">
  <head>
    <!-- Required meta tags -->
    <meta charset="utf-8">
    <title>prometheus-metric-preview</title>
  </head>
  <body>
    <h1>Prometheus Metric Preview</h1>
  </body>
</html>
"""


@blueprint.route("/preview")
@token_required
def preview_query():
    validator = Validator(allow_unknown=True)
    if not validator.validate(request.args, PREVIEW_REQUEST_SCHEMA):
        return jsonify({"body": {"error": validator.errors}}), 400

    prom_conn = current_app.config["prometheus_connection"]

    query = request.args.get("query", type=str)
    preview_title = request.args.get("title", default="Prometheus Metric", type=str)
    try:
        logger.info("Querying prometheus for metric %s", query)

        result = prom_conn.custom_query_range(
            query=query,
            start_time=(datetime.now(timezone.utc) - timedelta(hours=1)),
            end_time=datetime.now(timezone.utc),
            step="300",
        )
    except PrometheusApiClientException as exc:
        logger.error("Failed to query prometheus with error: %s", str(exc))
        return jsonify({"error": "Error querying Prometheus", "message": str(exc)}), 500

    logger.info("Creating plot for query")
    plt.figure(figsize=(10, 6))
    for series in result:
        container_name = series["metric"].get("container", "unknown")
        timestamps = [
            datetime.fromtimestamp(float(value[0])).strftime("%H:%M")
            for value in series["values"]
        ]
        values = [float(value[1]) for value in series["values"]]
        plt.plot(timestamps, values, label=container_name)

    plt.title(preview_title)
    plt.xlabel("Time (hh:mm)")
    plt.ylabel("Value")
    plt.xticks(rotation=45)  # Rotate x-axis labels for better readability
    plt.legend(title="Container")
    plt.grid(True)

    img_buffer = io.BytesIO()
    plt.savefig(img_buffer, format="png", bbox_inches="tight")
    img_buffer.seek(0)
    plt.close()
    gc.collect()

    return Response(img_buffer, mimetype="image/png")


@blueprint.route("/health")
def health():
    prom_conn = current_app.config["prometheus_connection"]
    if prom_conn.check_prometheus_connection():
        logger.info("Prometheus connection is healthy")
        return "OK"

    logger.error("Failed to connect to prometheus with url: %s", prom_conn.url)
    return "Failed connecting to prometheus", 400


def start_http_server():
    app = Flask(__name__)
    app.config["prometheus_connection"] = PrometheusConnect(
        url=os.environ["PROMETHEUS_URL"], disable_ssl=True
    )
    app.register_blueprint(blueprint)

    logger.info("Starting HTTP server for prometheus-metric-preview")
    serve(
        app,
        host="0.0.0.0",
        port=os.environ.get("PREVIEW_PORT", "8000"),
    )


if __name__ == "__main__":
    start_http_server()
