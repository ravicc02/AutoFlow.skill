import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "autoflow.py"


def workflow_file(run: Path) -> Path:
    return run / ".autoflow" / "config" / "workflow.json"


def make_routing_capabilities_available(run: Path) -> None:
    path = workflow_file(run)
    workflow = json.loads(path.read_text(encoding="utf-8"))
    for action in workflow.get("capabilities", {}).get("image", {}).get("actions", {}).values():
        action["status"] = "available"
    office = workflow.get("capabilities", {}).get("office", {})
    if office:
        office["status"] = office["officecli_status"] = "available"
        office["word_backend"]["status"] = "available"
    path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class AutoFlowCliTests(unittest.TestCase):
    def test_direct_route_resolves_one_module_without_creating_workflow_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "direct-route",
                    "--module",
                    "image",
                    "--action",
                    "diagram",
                    "--json",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["$schema"], "autoflow/direct-route/1.0")
            self.assertEqual(payload["execution_mode"], "direct")
            self.assertEqual(payload["module"], "image")
            self.assertEqual(payload["action"], "diagram")
            self.assertFalse(payload["workflow_files_created"])
            self.assertEqual(payload["stop_gates"], [])
            self.assertTrue(payload["output_policy"]["workspace_initialization_required"])
            self.assertEqual(
                payload["output_policy"]["workspace_directories"],
                [".autoflow/intermediate", ".autoflow/runtime", "submit"],
            )
            self.assertTrue(payload["output_policy"]["submit_required"])
            self.assertFalse(payload["output_policy"]["managed_submit_required"])
            self.assertTrue(payload["output_policy"]["minimum_requested_outputs"])
            self.assertEqual(payload["output_policy"]["sidecars"], "only_when_requested_or_required")
            self.assertTrue(payload["output_policy"]["sidecar_formats_are_one_artifact_family"])
            self.assertTrue(Path(payload["module_file"]).is_file())
            self.assertTrue(all(Path(path).is_file() for path in payload["capability_files"]))
            self.assertEqual(list(root.iterdir()), [])

    def test_plan_review_packet_exposes_plan_contents_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / "request.md"
            request.write_text("Create one managed document with an auditable review.", encoding="utf-8")
            run = root / "run"
            initialized = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "init",
                    "--request-file",
                    str(request),
                    "--output-dir",
                    str(run),
                    "--recipe",
                    "document",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            make_routing_capabilities_available(run)

            config = run / ".autoflow" / "config"
            workflow = json.loads((config / "workflow.json").read_text(encoding="utf-8"))
            (config / "WORK_PLAN.md").write_text(
                """# Managed document plan

## 目标
生成一份经过结构检查的文档，并保留可复核的计划、需求映射和验证结果。目标、范围和最终文件均在执行前明确，避免用户只看到一个没有内容的确认问题。

## 需求与证据
R1 要求文档真实生成并通过验证，证据对应 office.document 与 office.validation，计划文件负责解释验收标准和产出位置。

## 工作流
使用 document recipe。可选调研和图片步骤按需求跳过，Office 步骤负责创建与验证，所有依赖和输出以 workflow.json 为准。

## 产物
最终产物是 Office 文档及其验证报告；路径在执行后登记，计划阶段先声明类型、用途和验收条件。

## 信息替换
本测试没有身份信息、模板占位符或其他待替换字段，因此明确记录为无，不猜测用户信息。

## 范围与约束
不生成无关图片，不创建额外交付包，不绕过计划审核，不把运行环境或缓存混入最终文档目录。

## 验收策略
检查文件存在、文档结构和验证报告，再将结果与 R1 映射；完成前向用户展示计划摘要和本计划的绝对路径。
""",
                encoding="utf-8",
            )
            requirement_map_path = config / "requirement_map.json"
            requirement_map = json.loads(requirement_map_path.read_text(encoding="utf-8"))
            requirement_map["requirements"] = [
                {
                    "id": "R1",
                    "description": "Create and validate the managed document",
                    "required": True,
                    "acceptance": ["Document and validation report exist"],
                    "evidence_artifacts": ["office.document", "office.validation"],
                    "validation": {"status": "pending", "evidence": ""},
                }
            ]
            requirement_map_path.write_text(
                json.dumps(requirement_map, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            reviewed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "review",
                    "--workflow",
                    str(workflow_file(run)),
                    "--gate",
                    "plan",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
            packet = json.loads(reviewed.stdout)
            self.assertEqual(packet["$schema"], "autoflow/gate-review/1.0")
            self.assertEqual(packet["gate"], "plan")
            self.assertTrue(packet["must_show_before_approval"])
            self.assertEqual(packet["summary"]["recipe"], "document")
            self.assertTrue(packet["summary"]["steps"])
            self.assertEqual(packet["summary"]["required_requirements"][0]["id"], "R1")
            self.assertTrue(Path(packet["review_file"]).is_absolute())
            self.assertEqual(Path(packet["review_file"]), config / "WORK_PLAN.md")
            self.assertIn("absolute WORK_PLAN.md path", packet["required_display"])

    def test_stop_gate_contract_requires_substantive_review_packets(self):
        contract = (ROOT / "references" / "stop-gates.md").read_text(encoding="utf-8")
        for gate in ("PLAN_STOP", "SOURCE_STOP", "VISUAL_STOP", "DELIVERY_STOP"):
            self.assertIn(f"## {gate}", contract)
        for required_phrase in (
            "What the task will produce",
            "Three to five candidate names",
            "actual new images",
            "Final deliverable inventory",
            "absolute path",
        ):
            self.assertIn(required_phrase, contract)
        self.assertIn("only says “ready”, “approve?”, “continue?”", contract)

    def test_integrations_command_reports_audited_catalog(self):
        completed = subprocess.run(
            [sys.executable, str(CLI), "integrations", "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["$schema"], "autoflow/integrations/1.0")
        self.assertEqual(
            {item["name"] for item in payload["integrations"]},
            {"impeccable", "minimax-docx", "nature-figure", "officecli"},
        )
        self.assertTrue(all(item["status"] in {"available", "missing", "blocked"} for item in payload["integrations"]))
        for item in payload["integrations"]:
            self.assertIn(item["type"], {"tool", "knowledge-only"})
            self.assertGreaterEqual(len(item["capabilities"]), 1)

    def test_capabilities_reports_integrated_backends(self):
        completed = subprocess.run(
            [sys.executable, str(CLI), "capabilities", "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["$schema"], "autoflow/capabilities/1.0")
        self.assertEqual(payload["capabilities"]["impeccable"]["backend"], "integrated-impeccable")
        self.assertEqual(payload["capabilities"]["office"]["backend"], "officecli")
        self.assertIn(payload["capabilities"]["office"]["status"], {"available", "blocked", "missing"})
        self.assertTrue(Path(payload["capabilities"]["office"]["engine_script"]).is_file())
        self.assertTrue(Path(payload["capabilities"]["office"]["validator_script"]).is_file())
        self.assertEqual(payload["capabilities"]["video"]["backend"], "integrated-video-process")
        self.assertIn(payload["capabilities"]["video"]["status"], {"available", "blocked", "missing"})
        self.assertTrue(Path(payload["capabilities"]["video"]["script"]).is_file())
        self.assertEqual(payload["capabilities"]["image"]["backend"], "integrated-image-assets")
        self.assertIn(payload["capabilities"]["image"]["status"], {"available", "partial", "blocked", "missing"})

    def test_env_check_reports_sanitized_configuration(self):
        completed = subprocess.run(
            [sys.executable, str(CLI), "env-check", "--json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["$schema"], "autoflow/env-report/1.0")
        self.assertFalse(payload["environment"]["secrets_exposed"])
        self.assertIn("model", payload["environment"]["image"])

    def test_route_returns_local_skill_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / "request.md"
            request.write_text("Create a project.", encoding="utf-8")
            run = root / "run"
            initialized = subprocess.run(
                [sys.executable, str(CLI), "init", "--request-file", str(request), "--output-dir", str(run), "--recipe", "project-delivery"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            make_routing_capabilities_available(run)
            routed = subprocess.run(
                [sys.executable, str(CLI), "route", "--workflow", str(workflow_file(run)), "--step", "build", "--json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(routed.returncode, 0, routed.stderr)
            payload = json.loads(routed.stdout)
            self.assertEqual(payload["step"]["id"], "build")
            self.assertEqual(payload["mode"], "compact")
            self.assertIn("impeccable", payload["skill_names"])
            self.assertNotIn("requesting-code-review", payload["skill_names"])
            self.assertNotIn("code-review-and-quality", payload["skill_names"])
            self.assertTrue(all(Path(path).is_file() for path in payload["skill_files"]))
            full = subprocess.run(
                [sys.executable, str(CLI), "route", "--workflow", str(workflow_file(run)), "--step", "build", "--json", "--full"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(full.returncode, 0, full.stderr)
            full_payload = json.loads(full.stdout)
            self.assertEqual(full_payload["mode"], "full")
            self.assertIn("impeccable", full_payload["skill_names"])
            self.assertNotIn("requesting-code-review", full_payload["skill_names"])

    def test_ppt_route_returns_integrated_local_capability_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / "request.md"
            request.write_text("Create a defense presentation.", encoding="utf-8")
            run = root / "run"
            initialized = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "init",
                    "--request-file",
                    str(request),
                    "--output-dir",
                    str(run),
                    "--recipe",
                    "presentation",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            make_routing_capabilities_available(run)
            routed = subprocess.run(
                [sys.executable, str(CLI), "route", "--workflow", str(workflow_file(run)), "--step", "ppt", "--json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(routed.returncode, 0, routed.stderr)
            payload = json.loads(routed.stdout)
            self.assertIn("office", payload["capability_names"])
            self.assertEqual(payload["capabilities"]["office"]["backend"], "officecli")
            self.assertTrue(all(Path(path).is_file() for path in payload["capability_files"]))

    def test_auto_init_records_a_compound_recipe_recommendation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / "request.md"
            request.write_text("学生管理系统源码、论文和答辩PPT", encoding="utf-8")
            run = root / "run"
            initialized = subprocess.run(
                [sys.executable, str(CLI), "init", "--request-file", str(request), "--output-dir", str(run), "--recipe", "auto"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            workflow = json.loads(workflow_file(run).read_text(encoding="utf-8"))
            self.assertEqual(workflow["recipe"], "project-report-and-slides")
            self.assertEqual(workflow["recipe_selection"]["selected"], "project-report-and-slides")
            self.assertEqual([step["id"] for step in workflow["steps"]], ["source", "build", "image", "word", "ppt", "package"])

    def test_student_management_delivery_smoke_keeps_plan_stop_and_routes_every_step(self):
        with tempfile.TemporaryDirectory() as temp:
            started = time.monotonic()
            root = Path(temp)
            request = root / "request.md"
            request.write_text(
                "学生管理系统：交付可运行源码、论文和答辩PPT；先搜索GitHub候选，用户选择后再改造。",
                encoding="utf-8",
            )
            run = root / "run"
            initialized = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "init",
                    "--request-file",
                    str(request),
                    "--output-dir",
                    str(run),
                    "--recipe",
                    "auto",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            make_routing_capabilities_available(run)
            workflow = json.loads(workflow_file(run).read_text(encoding="utf-8"))
            state = json.loads((run / ".autoflow" / "config" / "run_state.json").read_text(encoding="utf-8"))
            self.assertEqual(workflow["recipe"], "project-report-and-slides")
            self.assertTrue(state["gates"]["plan"]["active"])
            self.assertEqual(state["gates"]["plan"]["status"], "pending")
            self.assertEqual(state["gates"]["source"]["status"], "not_applicable")

            for step in workflow["steps"]:
                routed = subprocess.run(
                    [
                        sys.executable,
                        str(CLI),
                        "route",
                        "--workflow",
                        str(workflow_file(run)),
                        "--step",
                        step["id"],
                        "--json",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(routed.returncode, 0, routed.stderr)
                payload = json.loads(routed.stdout)
                self.assertEqual(payload["step"]["id"], step["id"])
                self.assertTrue(all(name == "impeccable" for name in payload["skill_names"]))
                self.assertNotIn("requesting-code-review", payload["skill_names"])
                self.assertTrue(all(Path(path).is_file() for path in payload["skill_files"]))

            next_state = subprocess.run(
                [sys.executable, str(CLI), "next", "--workflow", str(workflow_file(run))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(next_state.returncode, 0, next_state.stderr)
            self.assertEqual(json.loads(next_state.stdout)["ready_steps"], [])
            self.assertLess(time.monotonic() - started, 10.0, "compact planning/routing regression")

    def test_init_defaults_output_dir_to_request_file_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            task = root / "task-project"
            task.mkdir()
            request = task / "request.md"
            request.write_text("Build a managed report.", encoding="utf-8")
            # No --output-dir: the run must be created next to the request file
            # (the task project root), not at the workspace root.
            initialized = subprocess.run(
                [sys.executable, str(CLI), "init", "--request-file", str(request), "--recipe", "document"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            workflow = workflow_file(task)
            self.assertTrue(workflow.is_file())
            self.assertFalse((root / ".autoflow").exists())
            payload = json.loads(initialized.stdout)
            self.assertEqual(payload["workflow"], str(workflow.resolve()))
            with workflow.open(encoding="utf-8") as handle:
                data = json.load(handle)
            self.assertEqual(data["output_dir"], str(task.resolve()))

    def test_init_status_and_legacy_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / "request.md"
            request.write_text("Create a document.", encoding="utf-8")
            run = root / "run"
            completed = subprocess.run(
                [sys.executable, str(CLI), "init", "--request-file", str(request), "--output-dir", str(run), "--recipe", "document"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "initialized")

            unplanned = subprocess.run(
                [sys.executable, str(CLI), "validate", "--workflow", str(workflow_file(run))],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(unplanned.returncode, 1)
            validation_payload = json.loads(unplanned.stdout)
            self.assertEqual(validation_payload["status"], "invalid")
            self.assertTrue(any("WORK_PLAN.md" in error for error in validation_payload["errors"]))
            self.assertTrue(any("requirement_map.json" in error for error in validation_payload["errors"]))

            status = subprocess.run(
                [sys.executable, str(CLI), "status", "--workflow", str(workflow_file(run)), "--timings"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertEqual(status_payload["recipe"], "document")
            self.assertIn("total_active_seconds", status_payload)
            self.assertIn("total_gate_wait_seconds", status_payload)

            legacy = root / "legacy.json"
            legacy.write_text('{"template_path":"old.docx","output_docx":"result.docx"}', encoding="utf-8")
            failed = subprocess.run(
                [sys.executable, str(CLI), "status", "--workflow", str(legacy)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertIn("Legacy workflow detected", failed.stderr)


if __name__ == "__main__":
    unittest.main()
