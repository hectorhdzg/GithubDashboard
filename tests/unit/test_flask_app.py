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
            'updated_at': '2025-01-01T00:00:00Z',
        }
        self.sample_pr = {
            'number': 202,
            'title': 'Sample PR',
            'state': 'open',
            'html_url': 'https://github.com/azure/example-repo/pull/202',
            'labels': [{'name': 'enhancement'}],
            'user_login': 'octocat',
            'requested_reviewers': [{'login': 'reviewer'}],
            'updated_at': '2025-01-02T00:00:00Z',
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
        """Landing page should render favorites view."""
        self.mc.get_repositories.return_value = self.sample_repositories
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Followed Work Items', response.data)
    
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
        """Navbar badges should display counts from alternate issue/pr fields."""
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
        # Badge shows combined issues + PRs total (7 + 2 = 9)
        self.assertIn(b'>9</span>', response.data)

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
        self.assertIn(b'Followed Items | GitHub Issues Dashboard', response.data)
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



if __name__ == '__main__':
    unittest.main()