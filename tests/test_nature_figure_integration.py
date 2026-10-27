from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from env_config import env_report

INTEGRATION = ROOT / "integrations" / "nature-figure"
PLOTTER = INTEGRATION / "scripts" / "plot_templates.py"
SCHEMATIC = ROOT / "scripts" / "generate_scientific_schematic.py"
TYPES = INTEGRATION / "figure-types.json"


class NatureFigureIntegrationTests(unittest.TestCase):
    def test_integrated_taxonomy_keeps_chart_and_ai_families_distinct(self) -> None:
        taxonomy = json.loads(TYPES.read_text(encoding="utf-8"))
        routes = taxonomy["routes"]
        self.assertEqual(
            routes["image.chart"]["publication_templates"],
            ["volcano", "roc", "dotplot", "marginal", "paired"],
        )
        self.assertEqual(
            routes["image.ai"]["scientific_schematics"],
            ["graphical_abstract", "mechanism_diagram", "concept_illustration", "paper_schematic"],
        )

    def test_all_publication_templates_render_every_declared_export(self) -> None:
        taxonomy = json.loads(TYPES.read_text(encoding="utf-8"))
        templates = taxonomy["routes"]["image.chart"]["publication_templates"]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            for name in templates:
                prefix = output / name
                result = subprocess.run(
                    [sys.executable, str(PLOTTER), name, "--demo", "--output", str(prefix)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, f"{name}: {result.stdout}\n{result.stderr}")
                for suffix in (".svg", ".pdf", ".tiff", ".qa.json"):
                    artifact = prefix.with_suffix(suffix)
                    self.assertTrue(artifact.is_file(), f"{name} missing {suffix}")
                    self.assertGreater(artifact.stat().st_size, 0, f"{name} empty {suffix}")
                qa = json.loads(prefix.with_suffix(".qa.json").read_text(encoding="utf-8"))
                self.assertEqual(qa["template"], name)
                self.assertTrue(qa["demo"])
                self.assertGreater(qa["rows_plotted"], 0)

    def test_all_scientific_schematic_kinds_build_local_upstream_payloads(self) -> None:
        taxonomy = json.loads(TYPES.read_text(encoding="utf-8"))
        kinds = taxonomy["routes"]["image.ai"]["scientific_schematics"]
        for kind in kinds:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCHEMATIC),
                    "--dry-run",
                    "--title",
                    f"AutoFlow {kind}",
                    "--prompt",
                    f"Create a {kind.replace('_', ' ')} from supplied evidence.",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, f"{kind}: {result.stderr}")
            payload = json.loads(result.stdout)
            self.assertEqual(payload["provider"], "autoflow_env_upstream")
            self.assertEqual(payload["model"], env_report(ROOT)["image"]["model"])
            self.assertIn(kind.replace("_", " "), payload["prompt"])


if __name__ == "__main__":
    unittest.main()
