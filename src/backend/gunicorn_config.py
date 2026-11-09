"""Cloud WSGI settings; one process shares the map cache and Nominatim throttle."""

import os

bind = f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"
workers = 1
worker_class = "gthread"
threads = 4
# The planner emits heartbeats and ends a stream after 180 seconds.
timeout = 210
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
capture_output = True
