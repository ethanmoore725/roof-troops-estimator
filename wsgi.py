# ─────────────────────────────────────────────────────────────
# wsgi.py
# ─────────────────────────────────────────────────────────────

# This file exists purely so Gunicorn can do:  `import wsgi; app = wsgi.app`
# Rename “app” if your Flask instance is named differently.

from app import app  # noqa: F401
