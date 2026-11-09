"""HTTP entry point: serve the page, parse requests, and call the planning services.

Scheduling rules live in validator.py, not in these route handlers. The browser
can request one JSON result or a stream of observable research steps plus a result.
"""

import json
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from .models import PlanRequest, ValidationRequest
from .services.demo import example_request
from .services.pipeline import plan_trip
from .services.providers import ProviderError, PublicDataClient
from .services.toolbox import catalog, execute_tool
from .validator import validate_itinerary
from .streaming import stream_plan


def create_app(config=None, data_client=None):
    """Build an app with injectable public-data adapters for offline testing."""
    # main.py lives in src/backend/app; frontend assets are its sibling under src/.
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    app = Flask(__name__, template_folder=str(frontend), static_folder=str(frontend / "static"))
    app.config.update(MAX_CONTENT_LENGTH=256_000)
    app.config.update(config or {})
    client = data_client or PublicDataClient()
    planning_slots = threading.BoundedSemaphore(2)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", data_modes=["demo", "live"],
                       planners=["heuristic"], llm_connected=False)

    @app.get("/tools")
    def tools_page():
        return render_template("tools.html")

    @app.get("/api/tools")
    def tools_catalog():
        return jsonify(tools=catalog(), llm_connected=False)

    @app.post("/api/tools/<name>")
    def call_tool(name):
        return jsonify(execute_tool(name, request.get_json(), client))

    @app.get("/api/example")
    def example():
        return jsonify(example_request())

    @app.post("/validate")
    def validate():
        parsed = ValidationRequest.model_validate(request.get_json())
        result = validate_itinerary(parsed)
        return jsonify(result.model_dump(mode="json"))

    @app.post("/api/plan")
    def plan():
        parsed = PlanRequest.model_validate(request.get_json())
        return jsonify(plan_trip(parsed, client=client))

    @app.post("/api/plan/stream")
    def plan_with_progress():
        parsed = PlanRequest.model_validate(request.get_json())
        return stream_plan(parsed, client, planning_slots, app.logger)

    @app.errorhandler(ValidationError)
    def invalid_model(error):
        detail = json.loads(error.json(
            include_url=False, include_input=False, include_context=False))
        return jsonify(error="Invalid request", detail=detail), 422

    @app.errorhandler(ProviderError)
    def unavailable_provider(error):
        return jsonify(error=str(error), provider=error.provider,
                       research_steps=getattr(error, "research_steps", [])), 503

    @app.errorhandler(ValueError)
    def invalid_plan(error):
        return jsonify(error=str(error), research_steps=getattr(error, "research_steps", [])), 422

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    return app
