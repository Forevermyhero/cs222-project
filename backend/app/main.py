"""Flask transport layer. The validator remains usable without this module."""

import json
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from .models import PlanRequest, ValidationRequest
from .services.demo import example_request
from .services.pipeline import plan_trip
from .services.providers import ProviderError, PublicDataClient
from .validator import validate_itinerary


def create_app(config=None, data_client=None):
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    app = Flask(__name__, template_folder=str(frontend), static_folder=str(frontend / "static"))
    app.config.update(MAX_CONTENT_LENGTH=256_000,
                      PLANNER_API_KEY=os.environ.get("PLANNER_API_KEY"),
                      PLANNER_MODEL=os.environ.get("PLANNER_MODEL", "gpt-4.1-mini"))
    app.config.update(config or {})
    client = data_client or PublicDataClient()

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", data_modes=["demo", "live"],
                       planners=["heuristic", "openai"],
                       openai_configured=bool(app.config["PLANNER_API_KEY"]))

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
        return jsonify(plan_trip(parsed, client=client,
                                 api_key=app.config["PLANNER_API_KEY"],
                                 model=app.config["PLANNER_MODEL"]))

    @app.errorhandler(ValidationError)
    def invalid_model(error):
        detail = json.loads(error.json(
            include_url=False, include_input=False, include_context=False))
        return jsonify(error="Invalid request", detail=detail), 422

    @app.errorhandler(ProviderError)
    def unavailable_provider(error):
        return jsonify(error=str(error), provider=error.provider), 503

    @app.errorhandler(ValueError)
    def invalid_plan(error):
        return jsonify(error=str(error)), 422

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
