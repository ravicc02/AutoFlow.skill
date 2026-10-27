import sys
import unittest
import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_images
from image_size import SIZE_MATRIX, normalize_resolution, resolve_batch_size
from validate_prompt import validate_structure


class GenerateImageTaskTests(unittest.TestCase):
    def test_batch_edit_uses_fallback_after_primary_retries(self):
        with tempfile.TemporaryDirectory() as temp:
            info = {"index": 1, "total": 1, "name": "edit", "prompt": "fix",
                    "output_dir": temp, "resolution": "2880x2880", "ref_image": "reference.png",
                    "max_retries": 2, "retry_delay": 0, "model": "primary", "fallback_model": "secondary"}
            calls = []

            def generate(**kwargs):
                calls.append(kwargs["model"])
                return "output.png" if kwargs["model"] == "secondary" else None

            with patch.object(generate_images, "generate_image_single", side_effect=generate):
                result = generate_images.generate_image_task(info)
            self.assertEqual(calls, ["primary", "primary", "secondary"])
            self.assertTrue(result["fallback_used"])
            self.assertEqual(result["model"], "secondary")

    def test_parameter_matrix_matches_all_supported_tiers_and_ratios(self):
        self.assertEqual(SIZE_MATRIX, {
            "1K": {"1:1": "1024x1024", "3:2": "1536x1024", "2:3": "1024x1536",
                   "16:9": "1280x720", "9:16": "720x1280", "4:3": "1024x768",
                   "3:4": "768x1024", "21:9": "1280x544"},
            "2K": {"1:1": "2048x2048", "3:2": "2160x1440", "2:3": "1440x2160",
                   "16:9": "2560x1440", "9:16": "1440x2560", "4:3": "2048x1536",
                   "3:4": "1536x2048", "21:9": "2560x1088"},
            "4K": {"1:1": "2880x2880", "3:2": "3456x2304", "2:3": "2304x3456",
                   "16:9": "3840x2160", "9:16": "2160x3840", "4:3": "3200x2400",
                   "3:4": "2400x3200", "21:9": "3840x1600"},
        })
        self.assertEqual(normalize_resolution("2k_16_9"), "2560x1440")

    def test_auto_aspect_uses_reference_then_asset_type(self):
        with tempfile.TemporaryDirectory() as temp:
            reference = Path(temp) / "portrait.png"
            Image.new("RGB", (900, 1600)).save(reference)
            self.assertEqual(resolve_batch_size("4K", reference_image=str(reference)), ("2160x3840", "9:16"))
        self.assertEqual(resolve_batch_size("4K", asset_type="screenshot"), ("3840x2160", "16:9"))
        self.assertEqual(resolve_batch_size("4K", asset_type="illustration"), ("2880x2880", "1:1"))
        self.assertEqual(resolve_batch_size("2K", "21:9"), ("2560x1088", "21:9"))
        self.assertEqual(resolve_batch_size("4K", "3:2", asset_type="screenshot"), ("3456x2304", "3:2"))
        self.assertEqual(resolve_batch_size("2048x1152"), ("2048x1152", "16:9"))
        with self.assertRaisesRegex(ValueError, "conflicts"):
            resolve_batch_size("2048x1152", "9:16")
        with self.assertRaisesRegex(ValueError, "Unsupported aspect_ratio"):
            resolve_batch_size("4K", "5:4")

    def test_batch_default_is_4k_auto_without_upstream_request(self):
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "prompt_config.json"
            config_path.write_text(json.dumps({
                "total_count": 2, "output_dir": str(Path(temp) / "output"),
                "images": [
                    {"name": "img_001", "asset_type": "screenshot", "prompt": "Terminal"},
                    {"name": "img_002", "asset_type": "illustration", "prompt": "Portrait", "aspect_ratio": "2:3"},
                ],
            }), encoding="utf-8")
            tasks = []

            def record_task(task):
                tasks.append(task)
                return {"name": task["name"], "success": True, "skipped": False}

            with patch.object(generate_images, "parse_upstream", return_value=("https://example.test", "key")), \
                 patch.object(generate_images, "load_env_file", return_value={}), \
                 patch.object(generate_images, "generate_image_task", side_effect=record_task):
                generate_images.generate_from_config(str(config_path))

            sizes = {task["name"]: task["resolution"] for task in tasks}
            self.assertEqual(sizes, {"img_001": "3840x2160", "img_002": "2304x3456"})

    def test_template_4k_auto_passes_structural_validation(self):
        template = Path(__file__).resolve().parents[1] / "examples" / "prompt_config.TEMPLATE.json"
        config = json.loads(template.read_text(encoding="utf-8"))
        config["total_count"] = 1
        report = validate_structure(config, template.parent)
        self.assertEqual(report["overall_result"], "pass", report["checks"])

        config["images"][0]["aspect_ratio"] = "9:16"
        self.assertEqual(validate_structure(config, template.parent)["overall_result"], "pass")
        config["images"][0]["resolution"] = "3840x2160"
        report = validate_structure(config, template.parent)
        self.assertEqual(report["overall_result"], "fail")
        self.assertTrue(any("conflicts" in check["issue"] for check in report["checks"]))

    def test_screenshot_lint_allows_java_annotation_package_name(self):
        policy = {"screenshot_forbidden_terms": ["annotation"]}

        errors = generate_images.lint_prompt(
            policy,
            "controller",
            "Use the actual import org.springframework.web.bind.annotation.* in the Java source.",
            "screenshot_strict",
        )

        self.assertEqual(errors, [])

    def test_single_request_uses_requested_model_and_default_1k_resolution(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"data": [{"b64_json": base64.b64encode(b"image-bytes").decode()}]}

        with tempfile.TemporaryDirectory() as temp:
            with patch.object(generate_images.requests, "post", return_value=Response()) as post:
                generated = generate_images.generate_image_single(
                    prompt="A non-sensitive concept illustration.",
                    output_dir=temp,
                    filename="result",
                    base_url="https://images.example.test",
                    api_key="test-key",
                    model="custom-image-model",
                )

        self.assertTrue(generated.endswith("result.png"))
        request = post.call_args.kwargs["json"]
        self.assertEqual(request["model"], "custom-image-model")
        self.assertEqual(request["size"], "1024x1024")

    def test_batch_report_preserves_http_generation_error(self):
        task = {
            "index": 1,
            "total": 1,
            "name": "img_001",
            "prompt": "A non-sensitive prompt.",
            "output_dir": str(Path.cwd()),
            "resolution": "1024x1024",
            "max_retries": 1,
            "retry_delay": 0,
            "base_url": "https://images.example.test",
            "api_key": "test-key",
            "timeout": 5,
        }

        with patch.object(
            generate_images,
            "generate_image_single",
            side_effect=generate_images.ImageGenerationError(
                "HTTP 503 Service Unavailable at https://images.example.test/v1/images/generations"
            ),
        ):
            result = generate_images.generate_image_task(task)

        self.assertFalse(result["success"])
        self.assertIn("HTTP 503 Service Unavailable", result["error"])


if __name__ == "__main__":
    unittest.main()
