"""Deprecated combined app module.

Historically this file attempted to co-host the dashboard and sync service in a
single Flask process. That deployment model is no longer supported. Importing
it now raises to prevent stale usage.
"""

raise ImportError("combined_app.py has been removed; deploy dashboard and sync service separately")