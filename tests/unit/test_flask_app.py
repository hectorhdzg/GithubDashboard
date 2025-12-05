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

from app import app
from services.sync_client import SyncClient


class TestFlaskApp(unittest.TestCase):
    """Test cases for the main Flask application."""
    
    def setUp(self):
        """Set up test client and app context."""
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
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
        """Test the main dashboard route."""
        with patch.object(SyncClient, 'get_repositories', return_value=self.sample_repositories):
            response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!DOCTYPE html>', response.data)
        self.assertIn(b'Select a repository from the navigation bar', response.data)
    
    def test_dashboard_with_repository_shows_issues(self):
        """Selecting a repository renders issue data."""
        with patch.object(SyncClient, 'get_repositories', return_value=self.sample_repositories), \
             patch.object(SyncClient, 'get_repository_issues', return_value=[self.sample_issue]):
            response = self.client.get('/?repo=azure/example-repo&type=issues&state=open')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Example Repo', response.data)
        self.assertIn(b'Sample Issue', response.data)
    
    def test_dashboard_with_repository_prs(self):
        """Selecting pull requests shows PR data."""
        with patch.object(SyncClient, 'get_repositories', return_value=self.sample_repositories), \
             patch.object(SyncClient, 'get_repository_pull_requests', return_value=[self.sample_pr]):
            response = self.client.get('/?repo=azure/example-repo&type=prs&state=open')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Sample PR', response.data)
        self.assertIn(b'Reviewers', response.data)

    def test_unknown_repository_returns_404(self):
        """Unknown repository should return 404."""
        with patch.object(SyncClient, 'get_repositories', return_value=self.sample_repositories):
            response = self.client.get('/?repo=azure/does-not-exist')
        self.assertEqual(response.status_code, 404)
    
    def test_nonexistent_route(self):
        """Test that nonexistent routes return 404."""
        response = self.client.get('/nonexistent')
        self.assertEqual(response.status_code, 404)
    
    def test_template_rendering(self):
        """Test that templates are rendered correctly."""
        # Test dashboard template has expected structure
        with patch.object(SyncClient, 'get_repositories', return_value=self.sample_repositories):
            response = self.client.get('/')
        self.assertIn(b'GitHub Issues Dashboard', response.data)
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
    
    @patch('app.app.run')
    def test_app_runs_with_correct_config(self, mock_run):
        """Test that app runs with correct configuration when executed directly."""
        # Set environment variable for testing
        with patch.dict('os.environ', {'PORT': '8001'}):
            # Import and run the app module's main block
            exec(open(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'app.py')).read())
            
            # Verify that app.run was called with correct parameters
            mock_run.assert_called_with(host="0.0.0.0", port=8001, debug=False)
    
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