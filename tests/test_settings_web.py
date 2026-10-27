from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from scripts.env_config import parse_env_file
from scripts.settings_config import public_settings, update_settings
from scripts.skill_packages import canonical_github_url, delete_skill, install_skill, installed_skills


class SettingsTests(unittest.TestCase):
    def test_settings_preserve_secrets_and_reject_injection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env").write_text("APIKEY:original-secret\nBASEURL:https://example.test\n", encoding="utf-8")
            update_settings(root, {"APIKEY": "", "IMAGE_MODEL": "image-v2", "IMAGE_EDIT_MAX_RETRIES": "3"})
            parsed = parse_env_file(root / ".env")
            self.assertEqual(parsed["APIKEY"], "original-secret")
            self.assertEqual(parsed["IMAGE_MODEL"], "image-v2")
            self.assertNotIn("original-secret", json.dumps(public_settings(root)))
            with self.assertRaises(ValueError):
                update_settings(root, {"IMAGE_MODEL": "model\nAPIKEY=bad"})
            with self.assertRaises(ValueError):
                update_settings(root, {"IMAGE_EDIT_MAX_RETRIES": "0"})

    def test_git_url_and_managed_delete(self):
        self.assertEqual(canonical_github_url("https://github.com/Owner/repo.git")[1], "owner--repo")
        for url in ("http://github.com/o/r", "https://evil.test/o/r", "https://github.com/o/r/tree/main", "https://github.com/o/r.git?x=1"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                canonical_github_url(url)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "keep.txt"
            outside.write_text("keep", encoding="utf-8")

            def fake_run(args, **kwargs):
                if "clone" in args:
                    source = Path(args[-1]); source.mkdir(parents=True)
                    (source / "SKILL.md").write_text("# Example", encoding="utf-8")
                    return type("Result", (), {"returncode": 0, "stdout": ""})()
                return type("Result", (), {"returncode": 0, "stdout": "abcd1234\n"})()

            with patch("scripts.skill_packages.subprocess.run", side_effect=fake_run):
                item = install_skill(root, "https://github.com/Owner/repo.git")
            self.assertEqual(item["status"], "available")
            self.assertEqual(item["id"], "github:owner--repo")
            self.assertEqual(len(installed_skills(root)), 1)
            with self.assertRaises(ValueError):
                delete_skill(root, "../keep.txt")
            delete_skill(root, item["id"])
            self.assertEqual(installed_skills(root), [])
            self.assertTrue(outside.is_file())

    def test_http_secret_masking_and_csrf(self):
        from http.server import ThreadingHTTPServer
        from scripts.settings_web import make_handler
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env").write_text("APIKEY=local-private-token\n", encoding="utf-8")
            with patch("scripts.settings_web.integration_catalog", return_value=[]), patch(
                "scripts.settings_web.detect_office_backend", return_value={"word_backend": {"selected": "officecli", "status": "available"}, "officecli_status": "available"}
            ):
                server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(root, "test-csrf"))
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
                    conn.request("GET", "/api/state")
                    response = conn.getresponse()
                    body = response.read().decode()
                    self.assertEqual(response.status, 200)
                    self.assertNotIn("local-private-token", body)
                    self.assertTrue(json.loads(body)["settings"]["secrets"]["APIKEY"])
                    payload = json.dumps({"values": {"IMAGE_MODEL": "new-model", "APIKEY": ""}})
                    headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{server.server_port}"}
                    conn.request("POST", "/api/settings", payload, headers)
                    rejected = conn.getresponse(); rejected.read()
                    self.assertEqual(rejected.status, 403)
                    conn.request("POST", "/api/settings", payload, {**headers, "X-CSRF-Token": "test-csrf"})
                    result = conn.getresponse(); result.read()
                    self.assertEqual(result.status, 200)
                    values = parse_env_file(root / ".env")
                    self.assertEqual(values["APIKEY"], "local-private-token")
                    self.assertEqual(values["IMAGE_MODEL"], "new-model")
                    conn.close()
                finally:
                    server.shutdown(); server.server_close(); thread.join()

    def test_explicit_missing_word_skill_blocks_instead_of_fallback(self):
        from scripts.autoflow_core import AutoFlowError, detect_office_backend, route_for_direct, route_for_workflow
        with patch("scripts.autoflow_core.load_skill_env", return_value={"WORD_AUTHORING_SKILL": "github:missing"}), patch(
            "scripts.autoflow_core.installed_skills", return_value=[]
        ):
            backend = detect_office_backend()
        self.assertEqual(backend["word_backend"]["selected"], "github:missing")
        self.assertEqual(backend["word_backend"]["status"], "missing")
        self.assertEqual(backend["status"], "blocked")
        with patch("scripts.autoflow_core.load_skill_env", return_value={"WORD_AUTHORING_SKILL": "officecli"}):
            route = route_for_direct("office", "edit", "word")
        self.assertEqual(route["authoring_skill"], "officecli")
        self.assertTrue(any(Path(path).name == "SKILL.md" for path in route["skill_files"]))
        step = {"id": "word", "module": "office", "action": "edit", "format": "word"}
        workflow = {"workflow_id": "test", "steps": [step], "capabilities": {
            "office": {"word_backend": {"selected": "github:gone", "skill_file": "missing/SKILL.md"}}}}
        with self.assertRaisesRegex(AutoFlowError, "no longer installed"):
            route_for_workflow(workflow, {"steps": {"word": {"status": "ready"}}}, "word")


if __name__ == "__main__":
    unittest.main()
