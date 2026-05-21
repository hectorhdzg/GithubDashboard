"""Flask entry point for the dashboard application."""
from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
load_dotenv()
import time
from datetime import datetime, timedelta, timezone
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

    # -- Shared date-filtering helpers -----------------------------------
    _PRESET_DAYS = {"1w": 7, "2w": 14, "1m": 30, "3m": 90}

    def _parse_date_params(default_preset: str = "") -> tuple[str, str, str, Optional[datetime], Optional[datetime]]:
        """Parse date_preset / date_from / date_to from request.args.

        Args:
            default_preset: Preset to apply when no date params in URL.
                            Empty string means no date filtering.

        Returns (date_preset, date_from_str, date_to_str, date_from_dt, date_to_dt).
        date_from_dt / date_to_dt are None when no date filter is active.
        """
        date_preset = request.args.get("date_preset", "")
        date_from_str = request.args.get("date_from", "")
        date_to_str = request.args.get("date_to", "")
        now = datetime.now(timezone.utc)

        # Distinguish "no date params at all" (apply default) from
        # "date_preset explicitly empty" (user chose All-time).
        has_explicit_date_param = "date_preset" in request.args or "date_from" in request.args or "date_to" in request.args
        if not has_explicit_date_param:
            date_preset = default_preset

        if date_preset in _PRESET_DAYS:
            date_from_dt = now - timedelta(days=_PRESET_DAYS[date_preset])
            date_to_dt = now
            date_from_str = date_from_dt.strftime("%Y-%m-%d")
            date_to_str = date_to_dt.strftime("%Y-%m-%d")
        elif date_preset == "custom" or date_from_str or date_to_str:
            date_preset = "custom"
            if date_from_str:
                try:
                    date_from_dt = datetime.strptime(date_from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    date_from_dt = now - timedelta(days=7)
                    date_from_str = date_from_dt.strftime("%Y-%m-%d")
            else:
                date_from_dt = now - timedelta(days=7)
                date_from_str = date_from_dt.strftime("%Y-%m-%d")

            if date_to_str:
                try:
                    date_to_dt = datetime.strptime(date_to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)
                except ValueError:
                    date_to_dt = now
                    date_to_str = now.strftime("%Y-%m-%d")
            else:
                date_to_dt = now
                date_to_str = now.strftime("%Y-%m-%d")
        else:
            # No date filter active
            date_from_dt = None
            date_to_dt = None

        return date_preset, date_from_str, date_to_str, date_from_dt, date_to_dt

    def _in_date_range(item: Dict[str, Any], date_from: Optional[datetime], date_to: Optional[datetime]) -> bool:
        """Check if an item's created_at falls within [date_from, date_to].

        Returns True (include everything) when either bound is None.
        """
        if date_from is None or date_to is None:
            return True
        raw = item.get("created_at") or item.get("updated_at") or ""
        if not raw:
            return False
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return date_from <= dt <= date_to
        except (ValueError, TypeError):
            return False

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
        filter_author = request.args.get("author", "").strip().lower()
        filter_assignee = request.args.get("assignee", "").strip().lower()

        # Date filtering — default to 1w everywhere
        date_preset, date_from_str, date_to_str, date_from_dt, date_to_dt = _parse_date_params(default_preset="1w")

        selected_repo_lower = selected_repo.lower() if selected_repo else None
        selected_repo_slug = None
        if selected_repo_lower:
            parts = selected_repo_lower.split("/")
            selected_repo_slug = "/".join(parts[-2:]) if len(parts) >= 2 else selected_repo_lower

        repositories = _cached_repositories()
        sync_error = client.last_error
        if sync_error:
            logger.warning("Sync service error: %s (url=%s)", sync_error, client.base_url)
        grouped = group_repositories(repositories)

        active_repo: Optional[Dict[str, Any]] = None
        work_items: List[Dict[str, Any]] = []
        data_error: Optional[str] = None
        state_counts: Dict[str, int] = {"open": 0, "closed": 0, "all": 0}
        filtered_issue_count = 0
        filtered_pr_count = 0

        # When on the overview page (no repo selected) and date filtering is active,
        # compute counts from actual work items so totals match the date range.
        if not selected_repo and date_from_dt is not None:
            all_issues, all_prs = _cached_all_work_items(repositories)
            filtered_issues = [i for i in all_issues if _in_date_range(i, date_from_dt, date_to_dt)]
            filtered_prs = [p for p in all_prs if _in_date_range(p, date_from_dt, date_to_dt)]

            # Per-repo counts for the overview table
            repo_issue_counts: Dict[str, int] = {}
            repo_pr_counts: Dict[str, int] = {}
            for i in filtered_issues:
                r = i.get("repo", "")
                repo_issue_counts[r] = repo_issue_counts.get(r, 0) + 1
            for p in filtered_prs:
                r = p.get("repo", "")
                repo_pr_counts[r] = repo_pr_counts.get(r, 0) + 1

            totals = {
                "repositories": len(repositories),
                "open_issues": len(filtered_issues),
                "open_prs": len(filtered_prs),
            }
        else:
            totals = compute_totals(repositories)
            repo_issue_counts = {}
            repo_pr_counts = {}

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

                work_items = [item for item in data if _match_repo(item)]
                if not work_items and data:
                    # Log for debugging but do NOT fall back to unfiltered data
                    logger.warning("No items matched repo filter for %s (%d raw items)", selected_repo, len(data))

                # Filter by author (PR) or assignee (issue) if specified
                if filter_author:
                    def _match_author(item: Dict[str, Any]) -> bool:
                        user = item.get("user") or item.get("user_login") or item.get("author")
                        login = _extract_login(user)
                        return login == filter_author if login else False
                    work_items = [item for item in work_items if _match_author(item)]

                if filter_assignee:
                    def _match_assignee(item: Dict[str, Any]) -> bool:
                        assignees_raw = _normalize_list(item.get("assignees"))
                        if not assignees_raw and item.get("assignee"):
                            assignees_raw = _normalize_list(item.get("assignee"))
                        for a in assignees_raw:
                            login = _extract_login(a)
                            if login == filter_assignee:
                                return True
                        return False
                    work_items = [item for item in work_items if _match_assignee(item)]

                # Apply date filter
                work_items = [item for item in work_items if _in_date_range(item, date_from_dt, date_to_dt)]

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

            # Compute actual filtered counts for the repo-detail badge chips.
            # These reflect what the user can really see after all filters are applied.
            filtered_issue_count = 0
            filtered_pr_count = 0
            if active_repo:
                # Count for the current data_type from filtered work_items
                current_count = len(work_items)
                # Also fetch the OTHER type and apply the same repo + date filter
                if data_type == "issues":
                    filtered_issue_count = current_count
                    other_data = client.get_repository_pull_requests(selected_repo, state=state)
                    if isinstance(other_data, list):
                        other_items = [i for i in other_data if _match_repo(i)]
                        other_items = [i for i in other_items if _in_date_range(i, date_from_dt, date_to_dt)]
                        filtered_pr_count = len(other_items)
                else:
                    filtered_pr_count = current_count
                    other_data = client.get_repository_issues(selected_repo, state=state)
                    if isinstance(other_data, list):
                        other_items = [i for i in other_data if _match_repo(i)]
                        other_items = [i for i in other_items if _in_date_range(i, date_from_dt, date_to_dt)]
                        filtered_issue_count = len(other_items)

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
            state_counts=state_counts,
            all_repositories=repositories,
            filter_author=filter_author,
            filter_assignee=filter_assignee,
            date_preset=date_preset,
            date_from=date_from_str,
            date_to=date_to_str,
            repo_issue_counts=repo_issue_counts,
            repo_pr_counts=repo_pr_counts,
            filtered_issue_count=filtered_issue_count,
            filtered_pr_count=filtered_pr_count,
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

    @app.route("/notifications", endpoint="notifications")
    def notifications_view():
        repositories = _cached_repositories()
        grouped = group_repositories(repositories)
        totals = compute_totals(repositories)
        return render_template(
            "notifications/index.html",
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

    def _item_key(item: Dict[str, Any]) -> str:
        """Build a dedup key from an issue or PR."""
        url = item.get("html_url") or item.get("url") or ""
        if url:
            return url
        repo = item.get("repo", "")
        number = item.get("number", "")
        return f"{repo}#{number}" if number else ""

    def _cached_all_work_items(repositories: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Fetch all open issues and PRs across every repo (cached)."""
        key = "all_work_items"
        cached = _cache.get(key)
        if cached is not None:
            return cached

        all_issues: List[Dict[str, Any]] = []
        all_prs: List[Dict[str, Any]] = []
        seen_issues: set = set()
        seen_prs: set = set()
        for repo in repositories:
            repo_name = repo.get("repo", "")
            issues = client.get_repository_issues(repo_name, state="open")
            if isinstance(issues, list):
                for i in issues:
                    i.setdefault("repo", repo_name)
                    i["labels"] = _enrich_labels(_normalize_list(i.get("labels")))
                    k = _item_key(i)
                    if k and k in seen_issues:
                        continue
                    if k:
                        seen_issues.add(k)
                    all_issues.append(i)
            prs = client.get_repository_pull_requests(repo_name, state="open")
            if isinstance(prs, list):
                for p in prs:
                    p.setdefault("repo", repo_name)
                    p["labels"] = _enrich_labels(_normalize_list(p.get("labels")))
                    k = _item_key(p)
                    if k and k in seen_prs:
                        continue
                    if k:
                        seen_prs.add(k)
                    all_prs.append(p)

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
                date_from="",
                date_to="",
                date_preset="1w",
            )

        # Date filtering — team always defaults to 1w
        date_preset, date_from_str, date_to_str, date_from_dt, date_to_dt = _parse_date_params(default_preset="1w")

        all_issues, all_prs = _cached_all_work_items(repositories)

        filtered_issues = [i for i in all_issues if _in_date_range(i, date_from_dt, date_to_dt)]
        filtered_prs = [p for p in all_prs if _in_date_range(p, date_from_dt, date_to_dt)]

        team_stats = _build_team_stats(team_handles, filtered_issues, filtered_prs)

        return render_template(
            "team.html",
            grouped_repositories=grouped,
            team_stats=team_stats,
            team_handles=team_handles,
            no_config=False,
            date_from=date_from_str,
            date_to=date_to_str,
            date_preset=date_preset,
        )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    print(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
