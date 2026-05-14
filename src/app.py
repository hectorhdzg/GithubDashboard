"""Flask entry point for the dashboard application."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from cachetools import TTLCache
from flask import Flask, abort, jsonify, render_template, request

from services.sync_client import SyncClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    base_dir = os.path.dirname(__file__)
    template_folder = os.path.abspath(os.path.join(base_dir, "..", "templates"))
    static_folder = os.path.abspath(os.path.join(base_dir, "..", "static"))

    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    client = SyncClient()

    # Simple TTL cache for sync service responses (avoids hammering on every page load)
    _cache: TTLCache = TTLCache(maxsize=256, ttl=60)
    app._response_cache = _cache

    def _normalize_list(value: Any) -> List[Any]:
        """Convert assorted list-ish values (JSON strings, dicts, scalars) into a clean list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return [value]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [value]
        return [value]

    def _label_color_from_name(name: str) -> str:
        """Generate a deterministic, pleasant color hex from a label name."""
        if not name:
            return "6c757d"
        # Simple hash for stable hue
        h = sum(ord(c) for c in name) % 360
        # Convert HSL to hex (fixed saturation/lightness for readability)
        s = 65
        l = 45
        # Utility conversion
        def hsl_to_rgb(hue: float, sat: float, lig: float) -> tuple[int, int, int]:
            c = (1 - abs(2 * lig - 1)) * sat
            x = c * (1 - abs((hue / 60) % 2 - 1))
            m = lig - c / 2
            if 0 <= hue < 60:
                r1, g1, b1 = c, x, 0
            elif 60 <= hue < 120:
                r1, g1, b1 = x, c, 0
            elif 120 <= hue < 180:
                r1, g1, b1 = 0, c, x
            elif 180 <= hue < 240:
                r1, g1, b1 = 0, x, c
            elif 240 <= hue < 300:
                r1, g1, b1 = x, 0, c
            else:
                r1, g1, b1 = c, 0, x
            r, g, b = (int((r1 + m) * 255), int((g1 + m) * 255), int((b1 + m) * 255))
            return r, g, b

        r, g, b = hsl_to_rgb(h, s / 100, l / 100)
        return f"{r:02x}{g:02x}{b:02x}"

    def _category_color(name: Optional[str]) -> str:
        """Return a vivid, deterministic color for repository categories, including unknown ones."""
        key = (name or "general").strip().lower()

        # Deterministic assignment across a palette for any unknown category
        palette_cycle = [
            "#2563eb",
            "#22c55e",
            "#0ea5e9",
            "#f59e0b",
            "#f97316",
            "#e11d48",
            "#8b5cf6",
            "#14b8a6",
            "#a855f7",
            "#3b82f6",
            "#10b981",
            "#ef4444",
            "#fbbf24",
            "#6366f1",
        ]

        index = sum(ord(c) for c in key) % len(palette_cycle)
        return palette_cycle[index]

    def _enrich_labels(labels: List[Any]) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        for label in labels:
            if isinstance(label, dict):
                name = label.get("name") or label.get("label") or ""
                color = label.get("color") or _label_color_from_name(name)
                enriched.append({"name": name, "color": color})
            else:
                name = str(label)
                enriched.append({"name": name, "color": _label_color_from_name(name)})
        return enriched

    # Make helpers available to templates
    app.jinja_env.globals["category_color"] = _category_color

    @app.after_request
    def add_no_cache_headers(response: Flask.response_class):
        """Avoid browser caching of dashboard pages so tables always reflect latest data."""
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        # Content-Security-Policy: restrict script/style sources to self + known CDNs
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://code.jquery.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https://github.com https://avatars.githubusercontent.com; "
            "connect-src 'self'"
        )
        return response

    def _cached_repositories() -> List[Dict[str, Any]]:
        """Return repositories with a short TTL cache to reduce sync service load."""
        key = "repositories"
        cached = _cache.get(key)
        if cached is not None:
            return cached
        repos = client.get_repositories()
        _cache[key] = repos
        return repos

    @app.route("/health", endpoint="health")
    def health_view():
        """Health check endpoint for load balancers and monitoring."""
        status = {"status": "ok", "timestamp": time.time()}
        try:
            repos = client.get_repositories()
            status["sync_service"] = "connected" if repos is not None else "error"
            if client.last_error:
                status["sync_service"] = "error"
                status["sync_error"] = client.last_error
        except Exception as exc:
            status["sync_service"] = "error"
            status["sync_error"] = str(exc)
        code = 200 if status.get("sync_service") == "connected" else 503
        return jsonify(status), code

    def group_repositories(repositories: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        grouped: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        for repo in repositories:
            language = repo.get("language_group") or "Other"
            category = repo.get("main_category") or "General"
            grouped.setdefault(language, {}).setdefault(category, []).append(repo)
        # Sort languages and categories for deterministic rendering
        for language_categories in grouped.values():
            for category, repos in language_categories.items():
                language_categories[category] = sorted(repos, key=lambda r: r.get("display_name", r.get("repo", "")))
        return dict(sorted(grouped.items(), key=lambda item: item[0]))

    def compute_totals(repositories: List[Dict[str, Any]]) -> Dict[str, int]:
        totals = {
            "repositories": len(repositories),
            "open_issues": 0,
            "open_prs": 0,
        }
        def coerce_count(value: Any) -> Optional[int]:
            try:
                if value is None:
                    return None
                if isinstance(value, (int, float)):
                    return int(value)
                if isinstance(value, str) and value.strip():
                    return int(float(value))
            except (TypeError, ValueError):
                return None
            return None

        for repo in repositories:
            issue_sources = [
                repo.get("issues_open"),
                repo.get("open_issues"),
                repo.get("open_issues_count"),
                repo.get("issue_count"),
                repo.get("issueCount"),
            ]
            issues_summary = repo.get("issues")
            if isinstance(issues_summary, dict):
                issue_sources.append(issues_summary.get("open"))

            pr_sources = [
                repo.get("prs_open"),
                repo.get("open_prs"),
                repo.get("open_prs_count"),
                repo.get("pr_count"),
                repo.get("pull_request_count"),
                repo.get("pullRequestCount"),
            ]
            pr_summary = repo.get("pull_requests")
            if isinstance(pr_summary, dict):
                pr_sources.append(pr_summary.get("open"))

            issue_value = next((count for count in (coerce_count(value) for value in issue_sources) if count is not None), 0)
            pr_value = next((count for count in (coerce_count(value) for value in pr_sources) if count is not None), 0)

            totals["open_issues"] += issue_value
            totals["open_prs"] += pr_value
        return totals

    @app.route("/", endpoint="home")
    @app.route("/dashboard", endpoint="dashboard")
    def dashboard_view():
        data_type = request.args.get("type", "issues").lower()
        if data_type not in {"issues", "prs"}:
            data_type = "issues"

        state = request.args.get("state", "open").lower()
        if state not in {"open", "closed", "all"}:
            state = "open"

        selected_repo = request.args.get("repo")
        selected_repo_lower = selected_repo.lower() if selected_repo else None
        selected_repo_slug = None
        if selected_repo_lower:
            parts = selected_repo_lower.split("/")
            selected_repo_slug = "/".join(parts[-2:]) if len(parts) >= 2 else selected_repo_lower

        repositories = _cached_repositories()
        sync_error = client.last_error
        grouped = group_repositories(repositories)
        totals = compute_totals(repositories)
        sync_base_url = client.base_url

        active_repo: Optional[Dict[str, Any]] = None
        work_items: List[Dict[str, Any]] = []
        data_error: Optional[str] = None
        state_counts: Dict[str, int] = {"open": 0, "closed": 0, "all": 0}

        if selected_repo:
            active_repo = next((r for r in repositories if r.get("repo") == selected_repo), None)
            if active_repo is None:
                abort(404)

            if data_type == "prs":
                data = client.get_repository_pull_requests(selected_repo, state=state)
            else:
                data = client.get_repository_issues(selected_repo, state=state)

            if isinstance(data, list):
                # Client-side filter safeguard in case backend ignores repo parameter
                def _match_repo(item: Dict[str, Any]) -> bool:
                    if not selected_repo_lower:
                        return False

                    def eq(value: Any) -> bool:
                        if not isinstance(value, str):
                            return False
                        lower_val = value.lower()
                        return lower_val == selected_repo_lower or (selected_repo_slug and lower_val.endswith(selected_repo_slug))

                    for key in ("repo", "repository", "repository_full_name"):
                        if eq(item.get(key)):
                            return True

                    base_repo = item.get("base", {}).get("repo", {}) if isinstance(item.get("base"), dict) else {}
                    head_repo = item.get("head", {}).get("repo", {}) if isinstance(item.get("head"), dict) else {}
                    for repo_obj in (base_repo, head_repo):
                        if eq(repo_obj.get("full_name")):
                            return True
                        if eq(repo_obj.get("name")):
                            return True

                    html_url = item.get("html_url") or item.get("url") or item.get("repository_url") or ""
                    if isinstance(html_url, str):
                        lower_url = html_url.lower()
                        if selected_repo_lower in lower_url or (selected_repo_slug and selected_repo_slug in lower_url):
                            return True

                    return False

                work_items = [item for item in data if _match_repo(item)] or data
                if not work_items and data:
                    data_error = "No items matched the selected repository."

                # Track counts by state for chips
                for item in work_items:
                    item_state = (item.get("state") or "").lower()
                    if item_state in {"open", "closed"}:
                        state_counts[item_state] += 1
                    state_counts["all"] += 1

                # Normalize list-ish fields so templates don't show raw JSON strings
                for item in work_items:
                    item["labels"] = _enrich_labels(_normalize_list(item.get("labels")))
                    assignees = _normalize_list(item.get("assignees"))
                    if not assignees and item.get("assignee"):
                        assignees = _normalize_list(item.get("assignee"))
                    item["assignees"] = assignees

                    reviewers = _normalize_list(item.get("reviewers"))
                    requested_reviewers = _normalize_list(item.get("requested_reviewers"))
                    # Prefer requested_reviewers if present
                    item["requested_reviewers"] = requested_reviewers or reviewers
            else:
                work_items = []
                data_error = "Unable to load data from sync service."

        return render_template(
            "dashboard.html",
            grouped_repositories=grouped,
            totals=totals,
            data_type=data_type,
            state=state,
            selected_repo=selected_repo,
            active_repo=active_repo,
            work_items=work_items,
            data_error=data_error,
            sync_error=sync_error,
            sync_base_url=sync_base_url,
            state_counts=state_counts,
            all_repositories=repositories,
        )

    @app.route("/favorites", endpoint="favorites")
    def favorites_view():
        repositories = _cached_repositories()
        grouped = group_repositories(repositories)
        totals = compute_totals(repositories)
        return render_template(
            "favorites/index.html",
            grouped_repositories=grouped,
            totals=totals,
        )

    # -- Team analytics --------------------------------------------------
    def _get_team_handles() -> List[str]:
        """Return configured team GitHub handles from TEAM_HANDLES env var."""
        raw = os.environ.get("TEAM_HANDLES", "")
        return [h.strip().lower() for h in raw.split(",") if h.strip()]

    def _extract_login(user: Any) -> Optional[str]:
        """Pull a GitHub login from various payload shapes."""
        if isinstance(user, str):
            return user.lower()
        if isinstance(user, dict):
            login = user.get("login") or user.get("username") or user.get("name")
            return login.lower() if login else None
        return None

    def _cached_all_work_items(repositories: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch all open issues and PRs across every repo (cached)."""
        key = "all_work_items"
        cached = _cache.get(key)
        if cached is not None:
            return cached

        all_issues: List[Dict[str, Any]] = []
        all_prs: List[Dict[str, Any]] = []
        for repo in repositories:
            repo_name = repo.get("repo", "")
            issues = client.get_repository_issues(repo_name, state="open")
            if isinstance(issues, list):
                for i in issues:
                    i.setdefault("repo", repo_name)
                all_issues.extend(issues)
            prs = client.get_repository_pull_requests(repo_name, state="open")
            if isinstance(prs, list):
                for p in prs:
                    p.setdefault("repo", repo_name)
                all_prs.extend(prs)

        result = (all_issues, all_prs)
        _cache[key] = result
        return result

    def _build_team_stats(
        team_handles: List[str],
        all_issues: List[Dict[str, Any]],
        all_prs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Aggregate stats per team member handle."""
        members: Dict[str, Dict[str, Any]] = {}
        for handle in team_handles:
            members[handle] = {
                "handle": handle,
                "issues_assigned": [],
                "prs_authored": [],
                "prs_reviewing": [],
                "repos_active": set(),
            }

        # Issues assigned to team members
        for issue in all_issues:
            assignees_raw = _normalize_list(issue.get("assignees"))
            if not assignees_raw and issue.get("assignee"):
                assignees_raw = _normalize_list(issue.get("assignee"))
            for a in assignees_raw:
                login = _extract_login(a)
                if login and login in members:
                    members[login]["issues_assigned"].append(issue)
                    members[login]["repos_active"].add(issue.get("repo", ""))

        # PRs authored by or reviewing by team members
        for pr in all_prs:
            author = _extract_login(
                pr.get("user") or pr.get("user_login") or pr.get("author")
            )
            if author and author in members:
                members[author]["prs_authored"].append(pr)
                members[author]["repos_active"].add(pr.get("repo", ""))

            reviewers_raw = _normalize_list(pr.get("requested_reviewers"))
            if not reviewers_raw:
                reviewers_raw = _normalize_list(pr.get("reviewers"))
            for r in reviewers_raw:
                login = _extract_login(r)
                if login and login in members:
                    members[login]["prs_reviewing"].append(pr)
                    members[login]["repos_active"].add(pr.get("repo", ""))

        # Build per-repo breakdown for each member
        for m in members.values():
            repo_issues: Dict[str, int] = {}
            for issue in m["issues_assigned"]:
                r = issue.get("repo", "unknown")
                repo_issues[r] = repo_issues.get(r, 0) + 1
            repo_prs: Dict[str, int] = {}
            for pr in m["prs_authored"]:
                r = pr.get("repo", "unknown")
                repo_prs[r] = repo_prs.get(r, 0) + 1
            m["issues_by_repo"] = dict(sorted(repo_issues.items(), key=lambda x: x[1], reverse=True))
            m["prs_by_repo"] = dict(sorted(repo_prs.items(), key=lambda x: x[1], reverse=True))
            m["repos_active"] = sorted(m["repos_active"])

        # Sort members by total activity descending
        member_list = sorted(
            members.values(),
            key=lambda m: len(m["issues_assigned"]) + len(m["prs_authored"]) + len(m["prs_reviewing"]),
            reverse=True,
        )
        return {
            "members": member_list,
            "total_issues": len(all_issues),
            "total_prs": len(all_prs),
        }

    @app.route("/team", endpoint="team")
    def team_view():
        team_handles = _get_team_handles()
        repositories = _cached_repositories()
        grouped = group_repositories(repositories)

        if not team_handles:
            return render_template(
                "team.html",
                grouped_repositories=grouped,
                team_stats=None,
                team_handles=[],
                no_config=True,
            )

        all_issues, all_prs = _cached_all_work_items(repositories)
        team_stats = _build_team_stats(team_handles, all_issues, all_prs)

        return render_template(
            "team.html",
            grouped_repositories=grouped,
            team_stats=team_stats,
            team_handles=team_handles,
            no_config=False,
        )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    print(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
