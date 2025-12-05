"""Flask entry point for the dashboard application."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, abort, render_template, request

from services.sync_client import SyncClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    base_dir = os.path.dirname(__file__)
    template_folder = os.path.abspath(os.path.join(base_dir, "..", "templates"))
    static_folder = os.path.abspath(os.path.join(base_dir, "..", "static"))

    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    client = SyncClient()

    def classify_error(status: Optional[str], error_message: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """Categorize known error types for downstream highlighting."""
        normalized_status = (status or "").strip().lower()
        message = (error_message or "").strip()
        message_lower = message.lower()

        if "rate limit" in message_lower or "secondary rate" in message_lower or "too many requests" in message_lower or "abuse detection" in message_lower:
            return "rate_limit", "GitHub API rate limit"
        if "403" in message_lower and "github" in message_lower and "rate limit" not in message_lower:
            return "rate_limit", "GitHub API rate limit"
        if "timeout" in message_lower or "timed out" in message_lower:
            return "timeout", "Request timed out"
        if "connection reset" in message_lower or "connection aborted" in message_lower:
            return "network", "Network interruption"

        if normalized_status == "error" and not message:
            return "unknown_error", "Unknown sync failure"

        return None, None

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
            ]
            issues_summary = repo.get("issues")
            if isinstance(issues_summary, dict):
                issue_sources.append(issues_summary.get("open"))

            pr_sources = [
                repo.get("prs_open"),
                repo.get("open_prs"),
                repo.get("open_prs_count"),
            ]
            pr_summary = repo.get("pull_requests")
            if isinstance(pr_summary, dict):
                pr_sources.append(pr_summary.get("open"))

            issue_value = next((count for count in (coerce_count(value) for value in issue_sources) if count is not None), 0)
            pr_value = next((count for count in (coerce_count(value) for value in pr_sources) if count is not None), 0)

            totals["open_issues"] += issue_value
            totals["open_prs"] += pr_value
        return totals

    def summarize_sync_history(history: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "entries": len(history),
            "sessions": 0,
            "issues_new": 0,
            "issues_updated": 0,
            "prs_new": 0,
            "prs_updated": 0,
            "errors": 0,
            "not_modified_runs": 0,
            "repositories_total": 0,
            "repositories_with_changes": 0,
            "repositories_with_errors": 0,
            "repositories_no_changes": 0,
            "rate_limit_hits": 0,
            "rate_limit_repositories": [],
            "rate_limit_details": [],
            "error_repositories": [],
            "other_error_repositories": [],
            "repositories_overview": [],
            "top_change_repositories": [],
            "problem_repositories": [],
        }

        session_ids = set()
        unique_repositories = set()
        changed_repositories = set()
        error_repositories: Dict[str, Dict[str, Any]] = {}
        rate_limit_repositories: set[str] = set()
        repository_totals: Dict[str, Dict[str, Any]] = {}

        for entry in history:
            session_id = entry.get("sync_session_id")
            if session_id:
                session_ids.add(session_id)

            repository = entry.get("repository") or "Unknown repository"
            unique_repositories.add(repository)

            repo_stats = repository_totals.setdefault(
                repository,
                {
                    "issues_new": 0,
                    "issues_updated": 0,
                    "prs_new": 0,
                    "prs_updated": 0,
                    "runs": 0,
                    "change_runs": 0,
                    "errors": 0,
                    "not_modified_runs": 0,
                    "rate_limit": False,
                    "rate_limit_count": 0,
                    "latest_sync_date": None,
                    "latest_status": None,
                    "latest_session_id": None,
                    "latest_error_category": None,
                    "latest_error_message": None,
                    "latest_duration": None,
                    "sync_types": set(),
                },
            )

            issues_new = int(entry.get("issues_new") or 0)
            issues_updated = int(entry.get("issues_updated") or 0)
            prs_new = int(entry.get("prs_new") or 0)
            prs_updated = int(entry.get("prs_updated") or 0)

            summary["issues_new"] += issues_new
            summary["issues_updated"] += issues_updated
            summary["prs_new"] += prs_new
            summary["prs_updated"] += prs_updated

            repo_stats["issues_new"] += issues_new
            repo_stats["issues_updated"] += issues_updated
            repo_stats["prs_new"] += prs_new
            repo_stats["prs_updated"] += prs_updated
            repo_stats["runs"] += 1
            if issues_new or issues_updated or prs_new or prs_updated:
                repo_stats["change_runs"] += 1
            sync_type = entry.get("sync_type") or "unspecified"
            repo_stats["sync_types"].add(sync_type)

            if issues_new or issues_updated or prs_new or prs_updated:
                changed_repositories.add(repository)

            status = (entry.get("status") or "").lower()
            error_message = entry.get("error_message")
            is_error = status not in {"success", "not_modified"} or bool(error_message)
            sync_date = entry.get("sync_date")

            if is_error:
                summary["errors"] += 1
                error_code, error_label = classify_error(status, error_message)
                entry["error_code"] = error_code
                entry["error_category"] = error_label

                repo_error = error_repositories.setdefault(
                    repository,
                    {
                        "count": 0,
                        "messages": set(),
                        "labels": set(),
                        "latest": entry.get("sync_date"),
                    },
                )
                repo_error["count"] += 1
                if error_message:
                    repo_error["messages"].add(error_message.strip())
                if error_label:
                    repo_error["labels"].add(error_label)
                if error_code == "rate_limit":
                    rate_limit_repositories.add(repository)
                    summary["rate_limit_hits"] += 1
                    repo_stats["rate_limit"] = True
                    repo_stats["rate_limit_count"] += 1
                latest_entry = entry.get("sync_date")
                if latest_entry:
                    current_latest = repo_error.get("latest")
                    if current_latest is None or latest_entry > current_latest:
                        repo_error["latest"] = latest_entry
                repo_stats["errors"] += 1
            else:
                entry["error_code"] = None
                entry["error_category"] = None

            if status == "not_modified":
                summary["not_modified_runs"] += 1
                repo_stats["not_modified_runs"] += 1

            latest_sync_date = repo_stats["latest_sync_date"]
            if sync_date and (latest_sync_date is None or sync_date > latest_sync_date):
                repo_stats["latest_sync_date"] = sync_date
                repo_stats["latest_status"] = status or None
                repo_stats["latest_session_id"] = session_id
                repo_stats["latest_error_category"] = entry.get("error_category")
                repo_stats["latest_error_message"] = error_message
                repo_stats["latest_duration"] = entry.get("duration_seconds")

        if session_ids:
            summary["sessions"] = len(session_ids)
        else:
            summary["sessions"] = len(history)

        summary["repositories_total"] = len(unique_repositories)

        error_repo_names = set(error_repositories.keys())
        summary["repositories_with_changes"] = len(changed_repositories)
        summary["repositories_with_errors"] = len(error_repo_names)
        summary["repositories_no_changes"] = len(
            unique_repositories.difference(changed_repositories).difference(error_repo_names)
        )

        error_repository_list = []
        for repo_name, data in sorted(error_repositories.items(), key=lambda item: item[0]):
            messages = sorted(data["messages"])
            labels = sorted(data["labels"])
            error_repository_list.append(
                {
                    "repository": repo_name,
                    "count": data["count"],
                    "messages": messages,
                    "labels": labels,
                    "latest": data["latest"],
                }
            )

        summary["error_repositories"] = error_repository_list

        rate_limit_list = [item for item in error_repository_list if item["repository"] in rate_limit_repositories]
        summary["rate_limit_details"] = rate_limit_list
        summary["rate_limit_repositories"] = sorted(rate_limit_repositories)

        other_errors = [item for item in error_repository_list if item["repository"] not in rate_limit_repositories]
        summary["other_error_repositories"] = other_errors

        repositories_overview: List[Dict[str, Any]] = []
        for repo_name, data in repository_totals.items():
            change_total = data["issues_new"] + data["issues_updated"] + data["prs_new"] + data["prs_updated"]
            overview = {
                "repository": repo_name,
                "issues_new": data["issues_new"],
                "issues_updated": data["issues_updated"],
                "prs_new": data["prs_new"],
                "prs_updated": data["prs_updated"],
                "change_total": change_total,
                "runs": data["runs"],
                "change_runs": data["change_runs"],
                "not_modified_runs": data["not_modified_runs"],
                "errors": data["errors"],
                "rate_limit": data["rate_limit"],
                "rate_limit_count": data["rate_limit_count"],
                "latest_sync_date": data["latest_sync_date"],
                "latest_status": data["latest_status"],
                "latest_session_id": data["latest_session_id"],
                "latest_error_category": data["latest_error_category"],
                "latest_error_message": data["latest_error_message"],
                "latest_duration": data["latest_duration"],
                "sync_types": sorted(data["sync_types"]),
            }
            overview["success_runs"] = max(overview["runs"] - overview["errors"], 0)
            repositories_overview.append(overview)

        repositories_overview.sort(
            key=lambda item: (
                -int(item["rate_limit"]),
                -int(item["errors"] > 0),
                -item["change_total"],
                -item["change_runs"],
                item["repository"].lower(),
            )
        )

        summary["repositories_overview"] = repositories_overview
        summary["top_change_repositories"] = [item for item in repositories_overview if item["change_total"] > 0][:5]
        summary["problem_repositories"] = [item for item in repositories_overview if item["rate_limit"] or item["errors"]]

        return summary

    def group_sync_sessions(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: List[Dict[str, Any]] = []
        index: Dict[str, Dict[str, Any]] = {}

        for entry in history:
            session_id = entry.get("sync_session_id") or f"single-{entry.get('sync_date')}-{entry.get('repository')}-{entry.get('sync_type')}"
            group = index.get(session_id)
            if group is None:
                group = {
                    "session_id": entry.get("sync_session_id"),
                    "session_key": session_id,
                    "started_at": entry.get("sync_date"),
                    "entries": [],
                    "stats": {
                        "repositories": set(),
                        "issues_new": 0,
                        "issues_updated": 0,
                        "prs_new": 0,
                        "prs_updated": 0,
                        "errors": 0,
                        "status_counts": {"success": 0, "not_modified": 0, "error": 0, "other": 0},
                        "rate_limit_errors": 0,
                        "all_not_modified": False,
                    },
                }
                grouped.append(group)
                index[session_id] = group

            entry_copy = dict(entry)
            repo_name = entry_copy.get("repository") or "Unknown repository"
            group["entries"].append(entry_copy)
            group["stats"]["repositories"].add(repo_name)

            issues_new = int(entry_copy.get("issues_new") or 0)
            issues_updated = int(entry_copy.get("issues_updated") or 0)
            prs_new = int(entry_copy.get("prs_new") or 0)
            prs_updated = int(entry_copy.get("prs_updated") or 0)

            group["stats"]["issues_new"] += issues_new
            group["stats"]["issues_updated"] += issues_updated
            group["stats"]["prs_new"] += prs_new
            group["stats"]["prs_updated"] += prs_updated

            status = (entry_copy.get("status") or "").lower()
            error_message = entry_copy.get("error_message")
            is_error = status not in {"success", "not_modified"} or bool(error_message)

            error_code = entry_copy.get("error_code")
            error_label = entry_copy.get("error_category")
            if error_code is None and is_error:
                error_code, error_label = classify_error(status, error_message)
                entry_copy["error_code"] = error_code
                entry_copy["error_category"] = error_label

            entry_copy["is_error"] = is_error
            entry_copy["has_changes"] = bool(issues_new or issues_updated or prs_new or prs_updated)

            if is_error:
                group["stats"]["errors"] += 1
                if error_code == "rate_limit":
                    group["stats"]["rate_limit_errors"] += 1

            if status == "success":
                group["stats"]["status_counts"]["success"] += 1
            elif status == "not_modified":
                group["stats"]["status_counts"]["not_modified"] += 1
            elif status == "error":
                group["stats"]["status_counts"]["error"] += 1
            else:
                group["stats"]["status_counts"]["other"] += 1

        for group in grouped:
            repos_set = group["stats"].pop("repositories")
            group["stats"]["repositories"] = len(repos_set)
            counts = group["stats"]["status_counts"]
            total_entries = len(group["entries"])
            group["stats"]["all_not_modified"] = total_entries > 0 and counts["not_modified"] == total_entries

            def sort_key(item: Dict[str, Any]) -> Tuple[int, str]:
                repo = item.get("repository") or ""
                status_value = (item.get("status") or "").lower()
                if item.get("is_error") and item.get("error_code") == "rate_limit":
                    return (0, repo)
                if item.get("is_error"):
                    return (1, repo)
                if status_value == "success" and item.get("has_changes"):
                    return (2, repo)
                if status_value == "success":
                    return (3, repo)
                if status_value == "not_modified":
                    return (4, repo)
                return (5, repo)

            group["entries"].sort(key=sort_key)

        return grouped

    @app.route("/", endpoint="dashboard")
    def dashboard_view():
        data_type = request.args.get("type", "issues").lower()
        if data_type not in {"issues", "prs"}:
            data_type = "issues"

        state = request.args.get("state", "open").lower()
        if state not in {"open", "closed", "all"}:
            state = "open"

        selected_repo = request.args.get("repo")

        repositories = client.get_repositories()
        sync_error = client.last_error
        grouped = group_repositories(repositories)
        totals = compute_totals(repositories)
        sync_base_url = client.base_url

        active_repo: Optional[Dict[str, Any]] = None
        work_items: List[Dict[str, Any]] = []
        data_error: Optional[str] = None

        if selected_repo:
            active_repo = next((r for r in repositories if r.get("repo") == selected_repo), None)
            if active_repo is None:
                abort(404)

            if data_type == "prs":
                data = client.get_repository_pull_requests(selected_repo, state=state)
            else:
                data = client.get_repository_issues(selected_repo, state=state)

            if isinstance(data, list):
                work_items = data
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
        )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    print(f"Starting Flask app on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
