from __future__ import annotations

import os


bind = f"0.0.0.0:{int(os.environ.get('PORT', '8080'))}"
workers = 1
threads = 16
worker_class = "gthread"
timeout = 300
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
capture_output = True
