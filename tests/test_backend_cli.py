from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BackendCliSmokeTests(unittest.TestCase):
    def test_impeccable_adapter_check(self) -> None:
        adapter = ROOT / "integrations" / "impeccable" / "scripts" / "impeccable_adapter.mjs"
        result = subprocess.run(
            ["node", str(adapter), "check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=f"adapter check failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("integrated-impeccable", result.stdout)

    def test_impeccable_adapter_rejects_remote_url_scans(self) -> None:
        adapter = ROOT / "integrations" / "impeccable" / "scripts" / "impeccable_adapter.mjs"
        result = subprocess.run(
            ["node", str(adapter), "detect", "https://example.com"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("URL scans are disabled", result.stderr)

    def test_backend_help_commands(self) -> None:
        scripts = (
            "autoflow.py",
            "capture_frontend_screenshots.py",
            "generate_diagram_assets.py",
            "generate_images.py",
            "package_submission.py",
            "validate_office.py",
            "validate_prompt.py",
            "video_process.py",
        )

        for script in scripts:
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / script), "--help"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.assertEqual(
                    result.returncode,
                    0,
                    msg=f"{script} --help failed:\n{result.stdout}\n{result.stderr}",
                )

    def test_office_engine_reports_officecli_capability(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "office_engine.py"), "check", "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["backend"], "officecli")
        self.assertIn(payload["status"], {"available", "blocked", "missing"})
        self.assertEqual(result.returncode, 0 if payload["status"] == "available" else 1)
        self.assertFalse(payload["external_skill_required"])


if __name__ == "__main__":
    unittest.main()
