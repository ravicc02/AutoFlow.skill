from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from autoflow_core import route_for_direct


class DocumentationRouteTests(unittest.TestCase):
    def test_local_markdown_links_resolve(self):
        documents = [ROOT / "SKILL.md", ROOT / "README.md", ROOT / "integrations" / "README.md"]
        documents += list((ROOT / "modules").rglob("*.md"))
        documents += list((ROOT / "references").glob("*.md"))
        documents += list((ROOT / "docs" / "prompts").glob("*.md"))
        links = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")
        for document in documents:
            with self.subTest(document=document.relative_to(ROOT)):
                content = document.read_text(encoding="utf-8")
                for target in links.findall(content):
                    if target.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    path, _, anchor = target.partition("#")
                    resolved = (document.parent / path).resolve()
                    self.assertTrue(resolved.is_file(), f"{document}: missing {target}")
                    if anchor == "ai-image-size-matrix":
                        self.assertIn("## AI image size matrix", resolved.read_text(encoding="utf-8"))

    def test_all_module_routes_include_existing_guidance(self):
        routes = [("task", "research", None), ("image", "ai", None),
                  ("office", "edit", "word"), ("office", "create", "ppt"),
                  ("office", "fill", "excel"), ("video", "analyze", None),
                  ("package", "assemble", None)]
        for module, action, format_name in routes:
            with self.subTest(module=module, action=action, format=format_name):
                result = route_for_direct(module, action, format_name)
                files = result["module_files"]
                self.assertEqual(files[-1], result["module_file"])
                self.assertTrue(all(Path(path).is_file() for path in files))
                if module == "office":
                    self.assertEqual(Path(files[0]), ROOT / "modules" / "office.md")
                    self.assertEqual(Path(files[1]), ROOT / "modules" / "office" / f"{format_name}.md")
                else:
                    self.assertEqual(files, [result["module_file"]])

    def test_prompt_template_points_to_live_matrix(self):
        template = json.loads((ROOT / "examples" / "prompt_config.TEMPLATE.json").read_text(encoding="utf-8"))
        self.assertIn("references/image-routing-taxonomy.md#ai-image-size-matrix", template["_resolution_comment"])
        for obsolete in ("references/image-parameter-matrix.md", "references/integration-contract.md",
                         "docs/prompts/submission_package_rules.md"):
            self.assertFalse((ROOT / obsolete).exists())


if __name__ == "__main__":
    unittest.main()
