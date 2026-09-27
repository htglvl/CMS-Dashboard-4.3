"""Offline checks: python -m unittest discover -s cloudflare -p 'test_*.py'."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import deploy_worker as deployment


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.url_file = Path(self.temp.name) / "worker_url.txt"
        for target, value in (
            ("PUBLIC_URL_FILE", self.url_file),
            ("load_dotenv", Mock()),
        ):
            patcher = patch.object(deployment, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        config = deployment.tomllib.loads((deployment.ROOT / "cloudflare/wrangler.toml").read_text())
        self.namespace = config["kv_namespaces"][0]["id"]
        patcher = patch.dict(deployment.os.environ, {
            "CF_API_TOKEN": "test-token", "CF_ACCOUNT_ID": "test-account",
            "CF_KV_NAMESPACE_ID": self.namespace,
        }, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch.object(deployment.requests, "Session")
    def test_deploy_uploads_proxy_and_records_permanent_url(self, session_type):
        response = Mock(ok=True)
        response.json.return_value = {"success": True, "result": {"subdomain": "example"}}
        session_type.return_value.request.return_value = response
        deployment.deploy()
        self.assertEqual(self.url_file.read_text(), "https://cms.example.workers.dev")
        calls = session_type.return_value.request.call_args_list
        self.assertEqual([call.args[0] for call in calls], ["GET", "PUT", "POST"])
        metadata = json.loads(calls[1].kwargs["files"]["metadata"][1])
        self.assertEqual(metadata["bindings"][0]["namespace_id"], self.namespace)
        self.assertEqual(calls[2].kwargs["json"], {"enabled": True})

    @patch.object(deployment.requests, "Session")
    def test_api_rejection_does_not_leave_stale_address(self, session_type):
        self.url_file.write_text("https://stale.example")
        response = Mock(ok=False, status_code=403)
        response.json.return_value = {"success": False, "errors": [{"code": 10000}]}
        session_type.return_value.request.return_value = response
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            deployment.deploy()
        self.assertFalse(self.url_file.exists())

    @patch.object(deployment.requests, "Session")
    def test_namespace_mismatch_stops_before_network(self, session_type):
        deployment.os.environ["CF_KV_NAMESPACE_ID"] = "wrong"
        with self.assertRaisesRegex(RuntimeError, "must match"):
            deployment.deploy()
        session_type.assert_not_called()

    @patch.object(deployment.time, "sleep")
    @patch.object(deployment.requests, "get")
    def test_readiness_rejects_redirect_then_accepts_health(self, get, sleep):
        self.url_file.write_text("https://cms.example.workers.dev")
        get.side_effect = [Mock(status_code=302, text=""), Mock(status_code=200, text="ok")]
        deployment.wait_until_ready()
        self.assertEqual(get.call_count, 2)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])

    def test_readiness_timeout_is_failure(self):
        self.url_file.write_text("https://cms.example.workers.dev")
        with self.assertRaisesRegex(RuntimeError, "did not become ready"):
            deployment.wait_until_ready(timeout=0)


if __name__ == "__main__":
    unittest.main()
