"""Deprecated module retained for compatibility.

The canonical Flask application entry point lives in ``app.py``. Importing
this module raises an error so accidental dependencies are surfaced quickly.
"""

raise ImportError("app_new.py has been removed; import app.py instead")
