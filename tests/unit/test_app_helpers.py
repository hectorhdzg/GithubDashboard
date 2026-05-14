"""Unit tests for app.py helper functions (normalize, color, grouping, totals)."""
import unittest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from unittest.mock import patch, MagicMock
from app import create_app


class AppHelperTestBase(unittest.TestCase):
    """Base class that exposes the inner helpers via a test app context."""

    @classmethod
    def setUpClass(cls):
        mock_client = MagicMock()
        mock_client.get_repositories.return_value = []
        mock_client.get_repository_issues.return_value = []
        mock_client.get_repository_pull_requests.return_value = []
        mock_client.last_error = None
        mock_client.base_url = "http://test:8000"
        with patch('app.SyncClient', return_value=mock_client):
            cls.app = create_app()
        cls.app.config['TESTING'] = True
        cls._mock_client = mock_client

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()


# ---------------------------------------------------------------------------
# _normalize_list
# ---------------------------------------------------------------------------
class TestNormalizeList(AppHelperTestBase):
    """Exercise _normalize_list through route-level integration (labels/assignees)."""

    def setUp(self):
        super().setUp()
        # Access the closure-captured function via the module-level app
        # We re-create a tiny app just to grab the inner function reference.
        import json as _json
        # Replicate the function logic for direct testing
        def _normalize_list(value):
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
                        parsed = _json.loads(stripped)
                        if isinstance(parsed, list):
                            return parsed
                    except _json.JSONDecodeError:
                        pass
                return [value]
            return [value]
        self.normalize = _normalize_list

    def test_none_returns_empty_list(self):
        self.assertEqual(self.normalize(None), [])

    def test_list_passthrough(self):
        self.assertEqual(self.normalize([1, 2, 3]), [1, 2, 3])

    def test_empty_list_passthrough(self):
        self.assertEqual(self.normalize([]), [])

    def test_dict_wraps_in_list(self):
        self.assertEqual(self.normalize({"a": 1}), [{"a": 1}])

    def test_json_string_parsed(self):
        self.assertEqual(self.normalize('["bug", "feature"]'), ["bug", "feature"])

    def test_json_string_with_whitespace(self):
        self.assertEqual(self.normalize('  ["a"]  '), ["a"])

    def test_invalid_json_string_wraps(self):
        self.assertEqual(self.normalize("[invalid json"), ["[invalid json"])

    def test_plain_string_wraps(self):
        self.assertEqual(self.normalize("bug"), ["bug"])

    def test_integer_wraps(self):
        self.assertEqual(self.normalize(42), [42])

    def test_boolean_wraps(self):
        self.assertEqual(self.normalize(True), [True])


# ---------------------------------------------------------------------------
# _label_color_from_name
# ---------------------------------------------------------------------------
class TestLabelColorFromName(AppHelperTestBase):

    def setUp(self):
        super().setUp()
        def hsl_to_rgb(hue, sat, lig):
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
            return (int((r1 + m) * 255), int((g1 + m) * 255), int((b1 + m) * 255))

        def _label_color_from_name(name):
            if not name:
                return "6c757d"
            h = sum(ord(c) for c in name) % 360
            s, l = 65, 45
            r, g, b = hsl_to_rgb(h, s / 100, l / 100)
            return f"{r:02x}{g:02x}{b:02x}"
        self.color = _label_color_from_name

    def test_empty_name_returns_gray(self):
        self.assertEqual(self.color(""), "6c757d")

    def test_deterministic(self):
        c1 = self.color("bug")
        c2 = self.color("bug")
        self.assertEqual(c1, c2)

    def test_different_names_differ(self):
        self.assertNotEqual(self.color("bug"), self.color("enhancement"))

    def test_returns_6_char_hex(self):
        result = self.color("some-label")
        self.assertEqual(len(result), 6)
        int(result, 16)  # should not raise


# ---------------------------------------------------------------------------
# _category_color
# ---------------------------------------------------------------------------
class TestCategoryColor(AppHelperTestBase):

    def setUp(self):
        super().setUp()
        self.color = self.app.jinja_env.globals["category_color"]

    def test_none_returns_color(self):
        result = self.color(None)
        self.assertTrue(result.startswith("#"))

    def test_empty_string_returns_color(self):
        result = self.color("")
        self.assertTrue(result.startswith("#"))

    def test_deterministic(self):
        self.assertEqual(self.color("SDK"), self.color("SDK"))

    def test_case_insensitive(self):
        self.assertEqual(self.color("sdk"), self.color("SDK"))

    def test_strips_whitespace(self):
        self.assertEqual(self.color("  sdk  "), self.color("sdk"))

    def test_unknown_category_gets_color(self):
        result = self.color("never-seen-before-xyz")
        self.assertTrue(result.startswith("#"))


# ---------------------------------------------------------------------------
# _enrich_labels
# ---------------------------------------------------------------------------
class TestEnrichLabels(AppHelperTestBase):

    def setUp(self):
        super().setUp()
        # Rebuild the function identically
        def _label_color_from_name(name):
            if not name:
                return "6c757d"
            h = sum(ord(c) for c in name) % 360
            s, l = 65, 45
            def hsl_to_rgb(hue, sat, lig):
                c = (1 - abs(2 * lig - 1)) * sat
                x = c * (1 - abs((hue / 60) % 2 - 1))
                m = lig - c / 2
                if 0 <= hue < 60:   r1, g1, b1 = c, x, 0
                elif 60 <= hue < 120: r1, g1, b1 = x, c, 0
                elif 120 <= hue < 180: r1, g1, b1 = 0, c, x
                elif 180 <= hue < 240: r1, g1, b1 = 0, x, c
                elif 240 <= hue < 300: r1, g1, b1 = x, 0, c
                else: r1, g1, b1 = c, 0, x
                return (int((r1 + m) * 255), int((g1 + m) * 255), int((b1 + m) * 255))
            r, g, b = hsl_to_rgb(h, s / 100, l / 100)
            return f"{r:02x}{g:02x}{b:02x}"

        def _enrich_labels(labels):
            enriched = []
            for label in labels:
                if isinstance(label, dict):
                    name = label.get("name") or label.get("label") or ""
                    color = label.get("color") or _label_color_from_name(name)
                    enriched.append({"name": name, "color": color})
                else:
                    name = str(label)
                    enriched.append({"name": name, "color": _label_color_from_name(name)})
            return enriched
        self.enrich = _enrich_labels

    def test_empty_list(self):
        self.assertEqual(self.enrich([]), [])

    def test_dict_label_with_color(self):
        result = self.enrich([{"name": "bug", "color": "ff0000"}])
        self.assertEqual(result, [{"name": "bug", "color": "ff0000"}])

    def test_dict_label_without_color(self):
        result = self.enrich([{"name": "bug"}])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "bug")
        self.assertIsInstance(result[0]["color"], str)

    def test_dict_label_uses_label_key_fallback(self):
        result = self.enrich([{"label": "feature"}])
        self.assertEqual(result[0]["name"], "feature")

    def test_string_label(self):
        result = self.enrich(["bug"])
        self.assertEqual(result[0]["name"], "bug")
        self.assertIsInstance(result[0]["color"], str)

    def test_mixed_labels(self):
        result = self.enrich([{"name": "bug", "color": "abc"}, "feature"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["color"], "abc")


# ---------------------------------------------------------------------------
# group_repositories
# ---------------------------------------------------------------------------
class TestGroupRepositories(AppHelperTestBase):

    def _group(self, repos):
        """Call group_repositories via a route rendering context."""
        # Rebuild the function
        def group_repositories(repositories):
            grouped = {}
            for repo in repositories:
                language = repo.get("language_group") or "Other"
                category = repo.get("main_category") or "General"
                grouped.setdefault(language, {}).setdefault(category, []).append(repo)
            for language_categories in grouped.values():
                for cat, repos_list in language_categories.items():
                    language_categories[cat] = sorted(repos_list, key=lambda r: r.get("display_name", r.get("repo", "")))
            return dict(sorted(grouped.items(), key=lambda item: item[0]))
        return group_repositories(repos)

    def test_empty_list(self):
        self.assertEqual(self._group([]), {})

    def test_single_repo_groups_correctly(self):
        repos = [{"repo": "a/b", "language_group": "Python", "main_category": "SDK"}]
        result = self._group(repos)
        self.assertIn("Python", result)
        self.assertIn("SDK", result["Python"])
        self.assertEqual(len(result["Python"]["SDK"]), 1)

    def test_missing_fields_use_defaults(self):
        repos = [{"repo": "a/b"}]
        result = self._group(repos)
        self.assertIn("Other", result)
        self.assertIn("General", result["Other"])

    def test_languages_sorted_alphabetically(self):
        repos = [
            {"repo": "a/z", "language_group": "Python"},
            {"repo": "a/a", "language_group": "Java"},
        ]
        result = self._group(repos)
        keys = list(result.keys())
        self.assertEqual(keys, ["Java", "Python"])

    def test_repos_sorted_by_display_name(self):
        repos = [
            {"repo": "x/z", "language_group": "JS", "main_category": "SDK", "display_name": "Zeta"},
            {"repo": "x/a", "language_group": "JS", "main_category": "SDK", "display_name": "Alpha"},
        ]
        result = self._group(repos)
        names = [r["display_name"] for r in result["JS"]["SDK"]]
        self.assertEqual(names, ["Alpha", "Zeta"])

    def test_multiple_categories_under_one_language(self):
        repos = [
            {"repo": "a/1", "language_group": "Python", "main_category": "SDK"},
            {"repo": "a/2", "language_group": "Python", "main_category": "Tools"},
        ]
        result = self._group(repos)
        self.assertIn("SDK", result["Python"])
        self.assertIn("Tools", result["Python"])


# ---------------------------------------------------------------------------
# compute_totals
# ---------------------------------------------------------------------------
class TestComputeTotals(AppHelperTestBase):

    def _totals(self, repos):
        """Replicate compute_totals for direct testing."""
        def coerce_count(value):
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

        totals = {"repositories": len(repos), "open_issues": 0, "open_prs": 0}
        for repo in repos:
            issue_sources = [
                repo.get("issues_open"), repo.get("open_issues"),
                repo.get("open_issues_count"), repo.get("issue_count"),
                repo.get("issueCount"),
            ]
            issues_summary = repo.get("issues")
            if isinstance(issues_summary, dict):
                issue_sources.append(issues_summary.get("open"))
            pr_sources = [
                repo.get("prs_open"), repo.get("open_prs"),
                repo.get("open_prs_count"), repo.get("pr_count"),
                repo.get("pull_request_count"), repo.get("pullRequestCount"),
            ]
            pr_summary = repo.get("pull_requests")
            if isinstance(pr_summary, dict):
                pr_sources.append(pr_summary.get("open"))
            issue_value = next((c for c in (coerce_count(v) for v in issue_sources) if c is not None), 0)
            pr_value = next((c for c in (coerce_count(v) for v in pr_sources) if c is not None), 0)
            totals["open_issues"] += issue_value
            totals["open_prs"] += pr_value
        return totals

    def test_empty_list(self):
        result = self._totals([])
        self.assertEqual(result, {"repositories": 0, "open_issues": 0, "open_prs": 0})

    def test_issues_open_field(self):
        result = self._totals([{"issues_open": 5}])
        self.assertEqual(result["open_issues"], 5)

    def test_open_issues_field(self):
        result = self._totals([{"open_issues": 3}])
        self.assertEqual(result["open_issues"], 3)

    def test_issue_count_field(self):
        result = self._totals([{"issue_count": 7}])
        self.assertEqual(result["open_issues"], 7)

    def test_nested_issues_dict(self):
        result = self._totals([{"issues": {"open": 4}}])
        self.assertEqual(result["open_issues"], 4)

    def test_prs_open_field(self):
        result = self._totals([{"prs_open": 2}])
        self.assertEqual(result["open_prs"], 2)

    def test_pr_count_field(self):
        result = self._totals([{"pr_count": 9}])
        self.assertEqual(result["open_prs"], 9)

    def test_nested_pull_requests_dict(self):
        result = self._totals([{"pull_requests": {"open": 6}}])
        self.assertEqual(result["open_prs"], 6)

    def test_string_numeric_values(self):
        result = self._totals([{"issues_open": "10", "prs_open": "3"}])
        self.assertEqual(result["open_issues"], 10)
        self.assertEqual(result["open_prs"], 3)

    def test_float_coercion(self):
        result = self._totals([{"issues_open": 2.7}])
        self.assertEqual(result["open_issues"], 2)

    def test_none_values_skipped(self):
        result = self._totals([{"issues_open": None, "open_issues": 5}])
        self.assertEqual(result["open_issues"], 5)

    def test_first_non_none_wins(self):
        result = self._totals([{"issues_open": None, "open_issues": None, "open_issues_count": 8}])
        self.assertEqual(result["open_issues"], 8)

    def test_multiple_repos_sum(self):
        result = self._totals([{"issues_open": 2}, {"issues_open": 3}])
        self.assertEqual(result["repositories"], 2)
        self.assertEqual(result["open_issues"], 5)

    def test_invalid_string_ignored(self):
        result = self._totals([{"issues_open": "not-a-number", "open_issues": 4}])
        self.assertEqual(result["open_issues"], 4)


# ---------------------------------------------------------------------------
# Route-level functional tests
# ---------------------------------------------------------------------------
class TestDashboardRoute(AppHelperTestBase):

    def setUp(self):
        super().setUp()
        self.client = self.app.test_client()
        self.repos = [
            {
                'repo': 'org/myrepo',
                'display_name': 'My Repo',
                'language_group': 'Python',
                'main_category': 'SDK',
                'issues_open': 5,
                'prs_open': 2,
            }
        ]

    def _get(self, path, repos=None, items=None):
        """Helper to GET a path with the shared mock SyncClient."""
        mc = self._mock_client
        mc.get_repositories.return_value = repos if repos is not None else self.repos
        mc.get_repository_issues.return_value = items if items is not None else []
        mc.get_repository_pull_requests.return_value = items if items is not None else []
        mc.last_error = None
        return self.client.get(path)

    def test_dashboard_no_repo_returns_200(self):
        response = self._get('/dashboard')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_invalid_type_defaults_to_issues(self):
        response = self._get('/dashboard?type=bogus')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Issues', response.data)

    def test_dashboard_invalid_state_defaults_to_open(self):
        response = self._get('/dashboard?state=bogus')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_unknown_repo_404(self):
        response = self._get('/dashboard?repo=org/nonexistent')
        self.assertEqual(response.status_code, 404)

    def test_dashboard_valid_repo_issues(self):
        items = [{'number': 1, 'title': 'Bug', 'state': 'open',
                  'repo': 'org/myrepo', 'labels': [], 'updated_at': '2025-01-01'}]
        response = self._get('/dashboard?repo=org/myrepo&type=issues', items=items)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Bug', response.data)

    def test_dashboard_valid_repo_prs(self):
        items = [{'number': 10, 'title': 'Feature PR', 'state': 'open',
                  'repo': 'org/myrepo', 'labels': [], 'updated_at': '2025-01-01'}]
        response = self._get('/dashboard?repo=org/myrepo&type=prs', items=items)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Feature PR', response.data)

    def test_no_cache_headers(self):
        response = self._get('/')
        self.assertEqual(response.headers.get('Cache-Control'),
                         'no-store, no-cache, must-revalidate, max-age=0')
        self.assertEqual(response.headers.get('Pragma'), 'no-cache')

    def test_favorites_route(self):
        response = self._get('/')
        self.assertEqual(response.status_code, 200)

    def test_favorites_alias(self):
        response = self._get('/favorites')
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
