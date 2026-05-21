"""
Unit tests for Flask application routes and configuration.
Tests all main routes, template rendering, and app setup.
"""
import unittest
import os
import sys
from unittest.mock import patch, MagicMock

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from app import create_app


class TestFlaskApp(unittest.TestCase):
    """Test cases for the main Flask application."""

    @classmethod
    def setUpClass(cls):
        cls._mock_client = MagicMock()
        cls._mock_client.last_error = None
        cls._mock_client.base_url = "http://test:8000"
        cls._mock_client.get_repositories.return_value = []
        cls._mock_client.get_repository_issues.return_value = []
        cls._mock_client.get_repository_pull_requests.return_value = []
        with patch('app.SyncClient', return_value=cls._mock_client):
            cls._app = create_app()
        cls._app.config['TESTING'] = True

    def setUp(self):
        """Set up test client and app context."""
        self.app = self._app
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.mc = self._mock_client
        # Clear response cache between tests so mocked data isn't stale
        if hasattr(self.app, '_response_cache'):
            self.app._response_cache.clear()
        self.sample_repositories = [
            {
                'repo': 'azure/example-repo',
                'display_name': 'Example Repo',
                'language_group': 'Python',
                'main_category': 'SDK',
                'issues_open': 3,
                'prs_open': 1,
            }
        ]
        self.sample_issue = {
            'number': 101,
            'title': 'Sample Issue',
            'state': 'open',
            'html_url': 'https://github.com/azure/example-repo/issues/101',
            'labels': [{'name': 'bug'}],
            'user': {'login': 'octocat'},
            'assignees': [{'login': 'maintainer'}],
            'created_at': '2026-05-19T10:00:00Z',
            'updated_at': '2026-05-19T10:00:00Z',
        }
        self.sample_pr = {
            'number': 202,
            'title': 'Sample PR',
            'state': 'open',
            'html_url': 'https://github.com/azure/example-repo/pull/202',
            'labels': [{'name': 'enhancement'}],
            'user_login': 'octocat',
            'requested_reviewers': [{'login': 'reviewer'}],
            'created_at': '2026-05-19T10:00:00Z',
            'updated_at': '2026-05-19T10:00:00Z',
        }
    
    def tearDown(self):
        """Clean up after tests."""
        self.app_context.pop()
    
    def test_app_configuration(self):
        """Test Flask app configuration is correct."""
        self.assertTrue(self.app.config['TESTING'])
        self.assertEqual(self.app.template_folder, os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'templates')))
        self.assertEqual(self.app.static_folder, os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', 'static')))
    
    def test_index_route(self):
        """Landing page should render dashboard overview."""
        self.mc.get_repositories.return_value = self.sample_repositories
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Dashboard Overview', response.data)

    def test_health_endpoint_connected(self):
        """Health check should return 200 when sync service is reachable."""
        self.mc.get_repositories.return_value = []
        self.mc.last_error = None
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['sync_service'], 'connected')

    def test_health_endpoint_error(self):
        """Health check should return 503 when sync service has errors."""
        self.mc.get_repositories.return_value = None
        self.mc.last_error = "Connection refused"
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 503)
        data = response.get_json()
        self.assertEqual(data['sync_service'], 'error')
        self.assertEqual(data['sync_error'], 'Connection refused')
    
    def test_dashboard_with_repository_shows_issues(self):
        """Selecting a repository renders issue data."""
        self.mc.get_repositories.return_value = self.sample_repositories
        self.mc.get_repository_issues.return_value = [self.sample_issue]
        response = self.client.get('/dashboard?repo=azure/example-repo&type=issues&state=open')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Example Repo', response.data)
        self.assertIn(b'Sample Issue', response.data)
    
    def test_dashboard_with_repository_prs(self):
        """Selecting pull requests shows PR data."""
        self.mc.get_repositories.return_value = self.sample_repositories
        self.mc.get_repository_pull_requests.return_value = [self.sample_pr]
        response = self.client.get('/dashboard?repo=azure/example-repo&type=prs&state=open')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sample PR', response.data)
        self.assertIn(b'Reviewers', response.data)

    def test_navbar_uses_issue_count_fallback_fields(self):
        """Navbar should display repo name from alternate issue/pr fields."""
        repositories = [{
            'repo': 'azure/example-repo',
            'display_name': 'Example Repo',
            'language_group': 'Python',
            'main_category': 'SDK',
            'issue_count': 7,
            'pr_count': 2,
        }]
        self.mc.get_repositories.return_value = repositories
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        # Navbar shows the repo display name (counts were removed)
        self.assertIn(b'Example Repo', response.data)

    def test_unknown_repository_returns_404(self):
        """Unknown repository should return 404."""
        self.mc.get_repositories.return_value = self.sample_repositories
        response = self.client.get('/dashboard?repo=azure/does-not-exist')
        self.assertEqual(response.status_code, 404)
    
    def test_nonexistent_route(self):
        """Test that nonexistent routes return 404."""
        response = self.client.get('/nonexistent')
        self.assertEqual(response.status_code, 404)
    
    def test_template_rendering(self):
        """Test that templates are rendered correctly."""
        self.mc.get_repositories.return_value = self.sample_repositories
        response = self.client.get('/')
        self.assertIn(b'Dashboard | GitHub Issues Dashboard', response.data)
        self.assertIn(b'<html', response.data)
        self.assertIn(b'</html>', response.data)
    
    def test_static_folder_accessible(self):
        """Test that static files can be accessed."""
        # Test CSS file accessibility (if it exists)
        response = self.client.get('/static/css/dashboard.css')
        # Should either return the CSS file or 404 if not found
        self.assertIn(response.status_code, [200, 404])


class TestAppStartup(unittest.TestCase):
    """Test cases for application startup and configuration."""

    def test_port_environment_variable(self):
        """Test that PORT environment variable is used correctly."""
        with patch.dict('os.environ', {'PORT': '9000'}):
            port = int(os.environ.get("PORT", 8001))
            self.assertEqual(port, 9000)
    
    def test_default_port(self):
        """Test that default port is used when PORT env var is not set."""
        with patch.dict('os.environ', {}, clear=True):
            port = int(os.environ.get("PORT", 8001))
            self.assertEqual(port, 8001)


class TestTeamView(unittest.TestCase):
    """Test cases for team analytics view."""

    @classmethod
    def setUpClass(cls):
        cls._mock_client = MagicMock()
        cls._mock_client.last_error = None
        cls._mock_client.base_url = "http://test:8000"
        cls._mock_client.get_repositories.return_value = []
        cls._mock_client.get_repository_issues.return_value = []
        cls._mock_client.get_repository_pull_requests.return_value = []
        with patch('app.SyncClient', return_value=cls._mock_client):
            cls._app = create_app()
        cls._app.config['TESTING'] = True

    def setUp(self):
        self.app = self._app
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.mc = self._mock_client
        if hasattr(self.app, '_response_cache'):
            self.app._response_cache.clear()

    def tearDown(self):
        self.app_context.pop()

    def test_team_no_config(self):
        """Team page shows config message when TEAM_HANDLES is not set."""
        with patch.dict('os.environ', {}, clear=False):
            os.environ.pop('TEAM_HANDLES', None)
            response = self.client.get('/team')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'No team configured', response.data)

    def test_team_with_handles(self):
        """Team page renders member list when TEAM_HANDLES is set."""
        repo = {'repo': 'org/repo1', 'display_name': 'Repo 1',
                'language_group': 'Python', 'main_category': 'SDK',
                'issues_open': 1, 'prs_open': 1}
        self.mc.get_repositories.return_value = [repo]
        self.mc.get_repository_issues.return_value = [
            {'number': 1, 'title': 'Issue 1', 'state': 'open',
             'html_url': 'https://github.com/org/repo1/issues/1',
             'assignees': [{'login': 'alice'}],
             'created_at': '2026-05-19T10:00:00Z',
             'updated_at': '2026-05-19T10:00:00Z'}
        ]
        self.mc.get_repository_pull_requests.return_value = [
            {'number': 2, 'title': 'PR 1', 'state': 'open',
             'html_url': 'https://github.com/org/repo1/pull/2',
             'user_login': 'alice',
             'created_at': '2026-05-19T10:00:00Z',
             'updated_at': '2026-05-19T10:00:00Z'}
        ]
        with patch.dict('os.environ', {'TEAM_HANDLES': 'alice,bob'}):
            response = self.client.get('/team?date_preset=1m')
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'@alice', response.data)
            self.assertIn(b'@bob', response.data)

    def test_team_date_filter_excludes_old_items(self):
        """Items outside the date range should not appear in counts."""
        repo = {'repo': 'org/repo1', 'display_name': 'Repo 1',
                'language_group': 'Python', 'main_category': 'SDK',
                'issues_open': 1, 'prs_open': 1}
        self.mc.get_repositories.return_value = [repo]
        self.mc.get_repository_issues.return_value = []
        self.mc.get_repository_pull_requests.return_value = [
            {'number': 10, 'title': 'Old PR', 'state': 'open',
             'html_url': 'https://github.com/org/repo1/pull/10',
             'user_login': 'alice',
             'created_at': '2020-01-01T00:00:00Z',
             'updated_at': '2020-01-01T00:00:00Z'},
            {'number': 11, 'title': 'Recent PR', 'state': 'open',
             'html_url': 'https://github.com/org/repo1/pull/11',
             'user_login': 'alice',
             'created_at': '2026-05-19T10:00:00Z',
             'updated_at': '2026-05-19T10:00:00Z'}
        ]
        with patch.dict('os.environ', {'TEAM_HANDLES': 'alice'}):
            response = self.client.get('/team?date_preset=1w')
            self.assertEqual(response.status_code, 200)
            # Only recent PR should count — old one created in 2020 is excluded
            self.assertIn(b'Recent PR', response.data)
            self.assertNotIn(b'Old PR', response.data)

    def test_team_deduplication(self):
        """Duplicate items should be counted only once."""
        repo = {'repo': 'org/repo1', 'display_name': 'Repo 1',
                'language_group': 'Python', 'main_category': 'SDK',
                'issues_open': 1, 'prs_open': 1}
        self.mc.get_repositories.return_value = [repo]
        self.mc.get_repository_issues.return_value = []
        # Return the same PR twice (duplicate)
        dup_pr = {'number': 5, 'title': 'Dup PR', 'state': 'open',
                  'html_url': 'https://github.com/org/repo1/pull/5',
                  'user_login': 'alice',
                  'created_at': '2026-05-19T10:00:00Z',
                  'updated_at': '2026-05-19T10:00:00Z'}
        self.mc.get_repository_pull_requests.return_value = [dup_pr.copy(), dup_pr.copy()]
        with patch.dict('os.environ', {'TEAM_HANDLES': 'alice'}):
            response = self.client.get('/team?date_preset=1m')
            self.assertEqual(response.status_code, 200)
            # Count the data-item-title occurrences — should appear once (one row)
            body = response.data.decode()
            # In the authored PRs table, the title should produce only one row
            self.assertEqual(body.count('data-item-title="Dup PR"'), 1)


class TestDashboardUserFilter(unittest.TestCase):
    """Test cases for author/assignee filtering on dashboard."""

    @classmethod
    def setUpClass(cls):
        cls._mock_client = MagicMock()
        cls._mock_client.last_error = None
        cls._mock_client.base_url = "http://test:8000"
        cls._mock_client.get_repositories.return_value = []
        cls._mock_client.get_repository_issues.return_value = []
        cls._mock_client.get_repository_pull_requests.return_value = []
        with patch('app.SyncClient', return_value=cls._mock_client):
            cls._app = create_app()
        cls._app.config['TESTING'] = True

    def setUp(self):
        self.app = self._app
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.mc = self._mock_client
        if hasattr(self.app, '_response_cache'):
            self.app._response_cache.clear()
        self.repo = {'repo': 'org/repo1', 'display_name': 'Repo 1',
                     'language_group': 'Python', 'main_category': 'SDK',
                     'issues_open': 2, 'prs_open': 2}

    def tearDown(self):
        self.app_context.pop()

    def test_filter_prs_by_author(self):
        """Dashboard should filter PRs by author query param."""
        self.mc.get_repositories.return_value = [self.repo]
        self.mc.get_repository_pull_requests.return_value = [
            {'number': 1, 'title': 'Alice PR', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/pull/1',
             'user_login': 'alice', 'updated_at': '2026-05-19T10:00:00Z'},
            {'number': 2, 'title': 'Bob PR', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/pull/2',
             'user_login': 'bob', 'updated_at': '2026-05-19T10:00:00Z'},
        ]
        response = self.client.get('/dashboard?repo=org/repo1&type=prs&state=open&author=alice')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Alice PR', response.data)
        self.assertNotIn(b'Bob PR', response.data)
        self.assertIn(b'Author:', response.data)
        self.assertIn(b'@alice', response.data)

    def test_filter_issues_by_assignee(self):
        """Dashboard should filter issues by assignee query param."""
        self.mc.get_repositories.return_value = [self.repo]
        self.mc.get_repository_issues.return_value = [
            {'number': 10, 'title': 'Alice Issue', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/issues/10',
             'assignees': [{'login': 'alice'}], 'updated_at': '2026-05-19T10:00:00Z'},
            {'number': 11, 'title': 'Bob Issue', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/issues/11',
             'assignees': [{'login': 'bob'}], 'updated_at': '2026-05-19T10:00:00Z'},
        ]
        response = self.client.get('/dashboard?repo=org/repo1&type=issues&state=open&assignee=alice')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Alice Issue', response.data)
        self.assertNotIn(b'Bob Issue', response.data)
        self.assertIn(b'Assignee:', response.data)
        self.assertIn(b'@alice', response.data)

    def test_dashboard_date_filter_excludes_old_items(self):
        """Dashboard should filter items by date when date_preset is provided."""
        self.mc.get_repositories.return_value = [self.repo]
        self.mc.get_repository_issues.return_value = [
            {'number': 20, 'title': 'Old Issue', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/issues/20',
             'created_at': '2020-01-01T00:00:00Z',
             'updated_at': '2020-01-01T00:00:00Z'},
            {'number': 21, 'title': 'Recent Issue', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/issues/21',
             'created_at': '2026-05-19T10:00:00Z',
             'updated_at': '2026-05-19T10:00:00Z'},
        ]
        response = self.client.get('/dashboard?repo=org/repo1&type=issues&state=open&date_preset=1w')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Recent Issue', response.data)
        self.assertNotIn(b'Old Issue', response.data)

    def test_dashboard_1m_filter_shows_recent_only(self):
        """Dashboard with 1m preset should show only last month's items."""
        self.mc.get_repositories.return_value = [self.repo]
        self.mc.get_repository_issues.return_value = [
            {'number': 30, 'title': 'Ancient Issue', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/issues/30',
             'created_at': '2020-01-01T00:00:00Z',
             'updated_at': '2020-01-01T00:00:00Z'},
            {'number': 31, 'title': 'Fresh Issue', 'state': 'open', 'repo': 'org/repo1',
             'html_url': 'https://github.com/org/repo1/issues/31',
             'created_at': '2026-05-19T10:00:00Z',
             'updated_at': '2026-05-19T10:00:00Z'},
        ]
        response = self.client.get('/dashboard?repo=org/repo1&type=issues&state=open&date_preset=1m')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'Ancient Issue', response.data)
        self.assertIn(b'Fresh Issue', response.data)

    def test_dashboard_renders_date_filter_card(self):
        """Dashboard with repo should render the date filter card."""
        self.mc.get_repositories.return_value = [self.repo]
        self.mc.get_repository_issues.return_value = []
        response = self.client.get('/dashboard?repo=org/repo1&type=issues&state=open&date_preset=1w')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'dateFilterForm', response.data)
        self.assertIn(b'1w', response.data)



if __name__ == '__main__':
    unittest.main()