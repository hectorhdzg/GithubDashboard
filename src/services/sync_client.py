"""Thin client for talking to the local sync service.

This module keeps HTTP knowledge out of the view layer so the Flask routes can
focus on transforming the returned payloads into template-friendly structures.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class SyncClient:
    """Wrapper around the sync service REST API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 10,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("SYNC_SERVICE_URL") or "http://localhost:8000").rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.last_error: Optional[str] = None

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            self.last_error = None
            response = self.session.get(url, params=params or {}, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.warning("Sync service request failed for %s: %s", url, exc)
            self.last_error = f"{exc}"
            return None

    # High-level helpers -------------------------------------------------
    def get_repositories(self) -> List[Dict[str, Any]]:
        payload = self._get("api/repositories")
        if isinstance(payload, dict):
            # API v2 returns {"repositories": [...]}
            repos = payload.get("repositories", [])
        else:
            repos = payload or []
        if not isinstance(repos, list):
            logger.warning("Unexpected repositories payload shape: %s", type(repos))
            return []
        return repos

    def get_repository_issues(self, repository: str, state: str = "open") -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"repo": repository, "limit": 200}
        if state != "all":
            params["state"] = state
        payload = self._get("api/issues", params=params)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("issues"), list):
                return payload["issues"]
            if isinstance(payload.get("data"), list):
                return payload["data"]
        return []

    def get_repository_pull_requests(self, repository: str, state: str = "open") -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"repo": repository, "limit": 200}
        if state != "all":
            params["state"] = state
        payload = self._get("api/pull_requests", params=params)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("pull_requests"), list):
                return payload["pull_requests"]
            if isinstance(payload.get("data"), list):
                return payload["data"]
        return []

    def get_statistics(self) -> Dict[str, Any]:
        payload = self._get("api/statistics")
        return payload if isinstance(payload, dict) else {}

    def get_sync_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        payload = self._get("api/sync/history", params={"limit": limit})
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if isinstance(payload.get("sync_history"), list):
                return payload["sync_history"]
            if isinstance(payload.get("data"), list):
                return payload["data"]
        return []

    def get_scheduler_status(self) -> Dict[str, Any]:
        payload = self._get("api/scheduler/status")
        return payload if isinstance(payload, dict) else {}
