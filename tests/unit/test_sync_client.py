"""Unit tests for SyncClient – HTTP wrapper around the sync service."""
import unittest
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

import requests
from services.sync_client import SyncClient


class TestSyncClientInit(unittest.TestCase):

    def test_default_base_url(self):
        with patch.dict(os.environ, {}, clear=True):
            client = SyncClient()
        self.assertEqual(client.base_url, "http://localhost:8000")

    def test_env_var_base_url(self):
        with patch.dict(os.environ, {"SYNC_SERVICE_URL": "http://myhost:9000/"}):
            client = SyncClient()
        self.assertEqual(client.base_url, "http://myhost:9000")

    def test_explicit_base_url(self):
        client = SyncClient(base_url="http://custom:1234/")
        self.assertEqual(client.base_url, "http://custom:1234")

    def test_default_timeout(self):
        client = SyncClient()
        self.assertEqual(client.timeout, 10)

    def test_custom_timeout(self):
        client = SyncClient(timeout=30)
        self.assertEqual(client.timeout, 30)

    def test_custom_session(self):
        session = requests.Session()
        client = SyncClient(session=session)
        self.assertIs(client.session, session)

    def test_last_error_initially_none(self):
        client = SyncClient()
        self.assertIsNone(client.last_error)


class TestSyncClientGet(unittest.TestCase):

    def setUp(self):
        self.session = MagicMock()
        self.client = SyncClient(base_url="http://test:8000", session=self.session)

    def test_successful_get(self):
        self.session.get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"ok": True}),
            raise_for_status=MagicMock(),
        )
        result = self.client._get("/api/test")
        self.assertEqual(result, {"ok": True})
        self.assertIsNone(self.client.last_error)

    def test_url_construction(self):
        self.session.get.return_value = MagicMock(
            json=MagicMock(return_value={}),
            raise_for_status=MagicMock(),
        )
        self.client._get("/api/repos")
        self.session.get.assert_called_once_with(
            "http://test:8000/api/repos", params={}, timeout=10,
        )

    def test_params_forwarded(self):
        self.session.get.return_value = MagicMock(
            json=MagicMock(return_value={}),
            raise_for_status=MagicMock(),
        )
        self.client._get("/api/issues", params={"state": "open"})
        self.session.get.assert_called_once_with(
            "http://test:8000/api/issues", params={"state": "open"}, timeout=10,
        )

    def test_request_exception_returns_none(self):
        self.session.get.side_effect = requests.exceptions.ConnectionError("fail")
        result = self.client._get("/api/test")
        self.assertIsNone(result)
        self.assertIn("fail", self.client.last_error)

    def test_timeout_returns_none(self):
        self.session.get.side_effect = requests.exceptions.Timeout("timeout")
        result = self.client._get("/api/test")
        self.assertIsNone(result)
        self.assertIn("timeout", self.client.last_error)

    def test_http_error_returns_none(self):
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
        self.session.get.return_value = resp
        result = self.client._get("/api/test")
        self.assertIsNone(result)

    def test_last_error_cleared_on_success(self):
        self.client.last_error = "old error"
        self.session.get.return_value = MagicMock(
            json=MagicMock(return_value={}),
            raise_for_status=MagicMock(),
        )
        self.client._get("/api/test")
        self.assertIsNone(self.client.last_error)


class TestGetRepositories(unittest.TestCase):

    def setUp(self):
        self.session = MagicMock()
        self.client = SyncClient(base_url="http://test:8000", session=self.session)

    def _mock_response(self, data):
        self.session.get.return_value = MagicMock(
            json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )

    def test_v2_response_dict(self):
        self._mock_response({"repositories": [{"repo": "a/b"}]})
        result = self.client.get_repositories()
        self.assertEqual(result, [{"repo": "a/b"}])

    def test_v1_response_list(self):
        self._mock_response([{"repo": "a/b"}])
        result = self.client.get_repositories()
        self.assertEqual(result, [{"repo": "a/b"}])

    def test_empty_repositories_key(self):
        self._mock_response({"repositories": []})
        result = self.client.get_repositories()
        self.assertEqual(result, [])

    def test_none_response(self):
        self.session.get.side_effect = requests.exceptions.ConnectionError("err")
        result = self.client.get_repositories()
        self.assertEqual(result, [])

    def test_unexpected_payload_shape(self):
        self._mock_response({"something_else": 123})
        result = self.client.get_repositories()
        self.assertEqual(result, [])


class TestGetRepositoryIssues(unittest.TestCase):

    def setUp(self):
        self.session = MagicMock()
        self.client = SyncClient(base_url="http://test:8000", session=self.session)

    def _mock_response(self, data):
        self.session.get.return_value = MagicMock(
            json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )

    def test_list_response(self):
        self._mock_response([{"number": 1}])
        result = self.client.get_repository_issues("org/repo")
        self.assertEqual(result, [{"number": 1}])

    def test_dict_with_issues_key(self):
        self._mock_response({"issues": [{"number": 2}]})
        result = self.client.get_repository_issues("org/repo")
        self.assertEqual(result, [{"number": 2}])

    def test_dict_with_data_key(self):
        self._mock_response({"data": [{"number": 3}]})
        result = self.client.get_repository_issues("org/repo")
        self.assertEqual(result, [{"number": 3}])

    def test_state_param_forwarded(self):
        self._mock_response([])
        self.client.get_repository_issues("org/repo", state="closed")
        call_args = self.session.get.call_args
        self.assertEqual(call_args[1]["params"]["state"], "closed")

    def test_state_all_omits_state_param(self):
        self._mock_response([])
        self.client.get_repository_issues("org/repo", state="all")
        call_args = self.session.get.call_args
        self.assertNotIn("state", call_args[1]["params"])

    def test_error_returns_empty_list(self):
        self.session.get.side_effect = requests.exceptions.ConnectionError("err")
        result = self.client.get_repository_issues("org/repo")
        self.assertEqual(result, [])


class TestGetRepositoryPullRequests(unittest.TestCase):

    def setUp(self):
        self.session = MagicMock()
        self.client = SyncClient(base_url="http://test:8000", session=self.session)

    def _mock_response(self, data):
        self.session.get.return_value = MagicMock(
            json=MagicMock(return_value=data),
            raise_for_status=MagicMock(),
        )

    def test_list_response(self):
        self._mock_response([{"number": 10}])
        result = self.client.get_repository_pull_requests("org/repo")
        self.assertEqual(result, [{"number": 10}])

    def test_dict_with_pull_requests_key(self):
        self._mock_response({"pull_requests": [{"number": 20}]})
        result = self.client.get_repository_pull_requests("org/repo")
        self.assertEqual(result, [{"number": 20}])

    def test_dict_with_data_key(self):
        self._mock_response({"data": [{"number": 30}]})
        result = self.client.get_repository_pull_requests("org/repo")
        self.assertEqual(result, [{"number": 30}])

    def test_state_param_forwarded(self):
        self._mock_response([])
        self.client.get_repository_pull_requests("org/repo", state="closed")
        call_args = self.session.get.call_args
        self.assertEqual(call_args[1]["params"]["state"], "closed")

    def test_state_all_omits_state_param(self):
        self._mock_response([])
        self.client.get_repository_pull_requests("org/repo", state="all")
        call_args = self.session.get.call_args
        self.assertNotIn("state", call_args[1]["params"])

    def test_error_returns_empty_list(self):
        self.session.get.side_effect = requests.exceptions.ConnectionError("err")
        result = self.client.get_repository_pull_requests("org/repo")
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
