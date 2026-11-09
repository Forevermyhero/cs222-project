"""HTTP streaming adapter: publish actual planning progress without storing chat/jobs.

The domain validator is unaware of threads or HTTP. The queue here transports
public tool events to the browser; disconnects stop work at the next observation.
"""

import json
import queue
import threading
import time

from flask import Response, stream_with_context

from .services.pipeline import plan_trip
from .services.providers import ProviderError


class PlanCancelled(Exception):
    """The browser disconnected or stopped receiving progress."""


def stream_plan(parsed, client, slots, logger):
    if not slots.acquire(blocking=False):
        raise ProviderError("Planner", "Two plans are already running; please try again shortly.")
    events = queue.Queue(maxsize=128)
    cancelled = threading.Event()

    def send(event):
        if cancelled.is_set():
            raise PlanCancelled()
        try:
            events.put(event, timeout=1)
        except queue.Full:
            raise PlanCancelled() from None

    def worker():
        try:
            result = plan_trip(parsed, client=client, progress=send)
            send({"type": "result", "result": result})
        except PlanCancelled:
            pass
        except (ProviderError, ValueError) as error:
            if not cancelled.is_set():
                send({"type": "error", "error": str(error),
                      "provider": getattr(error, "provider", None),
                      "status": 503 if isinstance(error, ProviderError) else 422})
        except Exception:
            logger.exception("Unexpected planning failure")
            if not cancelled.is_set():
                send({"type": "error", "error": "An unexpected error prevented planning.",
                      "status": 500})
        finally:
            slots.release()

    def generate():
        deadline = time.monotonic() + 180
        try:
            while time.monotonic() < deadline:
                try:
                    event = events.get(timeout=10)
                except queue.Empty:
                    yield json.dumps({"type": "heartbeat"}) + "\n"
                    continue
                yield json.dumps(event) + "\n"
                if event["type"] in ("result", "error"):
                    return
            yield json.dumps({"type": "error", "status": 504,
                              "error": "Planning took too long; try fewer places."}) + "\n"
        finally:
            cancelled.set()

    # Start independently of body iteration so an abandoned response cannot leak a slot.
    threading.Thread(target=worker, daemon=True).start()
    response = Response(stream_with_context(generate()), content_type="application/x-ndjson",
                        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    response.call_on_close(cancelled.set)
    return response
