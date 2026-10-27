import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from autoflow_core import (  # noqa: E402
    AutoFlowError,
    _image_env_status,
    approve_gate,
    detect_impeccable_backend,
    detect_image_backend,
    detect_office_backend,
    detect_video_backend,
    gate_review_packet,
    hash_path,
    integration_catalog,
    initialize_run,
    load_json,
    load_run,
    refresh_ready,
    register_step_artifacts,
    recommend_recipe,
    revise_step,
    save_json,
    save_run,
    set_gate_state,
    sync_planning_state,
    transition_step,
    validate_run,
    validate_capabilities,
    validate_environment_report,
    validate_package_acceptance,
    validate_unpacked_final_locations,
    validate_video_acceptance,
    validate_workflow_definition,
    route_for_workflow,
    route_for_direct,
    workflow_capabilities,
)


COMPLETE_PLAN = """# Work Plan

## 目标
完成用户要求的真实产物，并用可复现验证证明结果满足要求。这里补充足够的目标说明，避免模板被误认为已经完成。

## 需求与证据
把每项需求映射到 workflow 声明的真实产物，并在 requirement_map.json 中记录验收条件、证据和状态。

## 工作流
先执行任务模块，再生成或捕获证据，然后装配目标文档或交付包。所有依赖、STOP 和验证都记录在 AutoFlow 状态文件中。

## 产物
产出 workflow 声明的全部文件、目录或压缩包；每个产物都有绝对路径、生产步骤、消费者和 SHA-256。

## 信息替换
本测试没有模板身份信息替换项，明确记录为无，不猜测或制造用户信息。

## 范围与约束
不制造虚假证据，不跳过用户批准，不把未声明的缓存或敏感文件装入交付包，所有测试只在临时目录运行。

## 验收策略
逐步检查声明产物、哈希、模块验证报告、需求证据映射和最终 delivery_review.json，再请求用户签收。
"""


class AutoFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = self.root / "request.md"
        self.request.write_text("Build the requested deliverables.", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def init(self, recipe):
        workflow_path = initialize_run(self.request, self.root / "run", recipe)
        workflow, state, manifest, paths = load_run(workflow_path)
        paths["work_plan"].write_text(COMPLETE_PLAN, encoding="utf-8")
        evidence = [
            artifact_id
            for step in workflow["steps"]
            if not step.get("optional", False)
            for artifact_id in step.get("outputs", [])
        ]
        save_json(
            paths["requirement_map"],
            {
                "$schema": "autoflow/requirement-map/1.0",
                "workflow_id": workflow["workflow_id"],
                "status": "planning",
                "target_tier": "tests-complete",
                "source_files": [str(self.request)],
                "requirements": [
                    {
                        "id": "R1",
                        "description": "Complete the declared workflow outputs",
                        "required": True,
                        "acceptance": ["Declared outputs exist and validate"],
                        "evidence_artifacts": evidence,
                        "validation": {"status": "pending", "evidence": ""},
                    }
                ],
                "planned_figures": [],
            },
        )
        approve_gate(workflow, state, manifest, paths, "plan", "User approved the complete work plan")
        save_run(state, manifest, paths)
        return workflow_path, workflow, state, manifest, paths

    def make_artifact(self, name, content="artifact"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_init_uses_hidden_control_dir_and_submit_dir(self):
        output = self.root / "autoflow"
        workflow_path = initialize_run(self.request, output, "document")
        expected_workflow = output / ".autoflow" / "config" / "workflow.json"
        self.assertEqual(workflow_path, expected_workflow)
        self.assertFalse((output / "workflow.json").exists())
        workflow, _, _, paths = load_run(workflow_path)
        self.assertEqual(paths["root"], output.resolve())
        self.assertEqual(paths["submit"], (output / "submit").resolve())
        self.assertEqual(paths["plans"], (output / ".autoflow" / "intermediate" / "plans").resolve())
        self.assertEqual(workflow["run_layout"], "autoflow/run-layout/1.0")
        self.assertEqual(Path(workflow["request_file"]), output / ".autoflow" / "config" / "request.md")
        self.assertTrue(Path(workflow["request_file"]).is_file())
        for directory in ("scripts", "intermediate", "config", "plans", "artifacts", "submit"):
            self.assertTrue(paths[directory].is_dir(), directory)

    def test_init_defaults_output_dir_to_request_file_directory(self):
        # Session workspace is the parent of the task project; the request file
        # lives inside the task project, so the run must be created there and
        # not at the workspace root.
        task_project = self.root / "task"
        task_project.mkdir()
        request = task_project / "request.md"
        request.write_text("Build the requested deliverables.", encoding="utf-8")
        workflow_path = initialize_run(request, None, "document")
        self.assertEqual(workflow_path, task_project / ".autoflow" / "config" / "workflow.json")
        self.assertTrue(workflow_path.is_file())
        workflow, _, _, paths = load_run(workflow_path)
        self.assertEqual(paths["root"], task_project.resolve())
        self.assertEqual(workflow["output_dir"], str(task_project.resolve()))

    def complete_step(self, workflow, state, manifest, paths, step_id, artifacts):
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, step_id, "running", "started", {})
        transition_step(workflow, state, manifest, paths, step_id, "completed", "verified", artifacts)

    def make_office_artifacts(self, base=None, format_name="word"):
        base = Path(base) if base else self.root
        base.mkdir(parents=True, exist_ok=True)
        suffix = {"word": ".docx", "ppt": ".pptx", "excel": ".xlsx"}[format_name]
        document = base / f"result{suffix}"
        document.write_text("minimal test document", encoding="utf-8")
        report = base / "office-validation.json"
        save_json(
            report,
            {
                "$schema": "autoflow/office-validation/1.0",
                "format": format_name,
                "document": {
                    "path": str(document.resolve()),
                    "sha256": hash_path(document),
                    "size": document.stat().st_size,
                },
                "checks": [{"name": "test_validation", "status": "passed", "evidence": "fixture"}],
                "overall_pass": True,
            },
        )
        return {"office.document": document, "office.validation": report}

    def prepare_delivery_review(self, workflow, manifest, paths):
        requirement_map = load_json(paths["requirement_map"])
        requirement_map["status"] = "verified"
        for item in requirement_map["requirements"]:
            item["validation"] = {"status": "passed", "evidence": "Automated test evidence passed"}
        save_json(paths["requirement_map"], requirement_map)
        save_json(
            paths["delivery_review"],
            {
                "$schema": "autoflow/delivery-review/1.0",
                "workflow_id": workflow["workflow_id"],
                "review_completed": True,
                "requirement_results": [
                    {
                        "id": item["id"],
                        "present": True,
                        "correct": True,
                        "evidence_artifacts": item["evidence_artifacts"],
                        "notes": "verified",
                    }
                    for item in requirement_map["requirements"]
                    if item["required"]
                ],
                "artifact_results": [
                    {"id": item["id"], "present": True, "correct": True, "notes": "verified"}
                    for item in manifest["artifacts"]
                ],
                "issues_found": [],
                "overall_pass": True,
                "reviewer_notes": "test review",
            },
        )

    def test_word_only_recipe_can_finish_and_requires_delivery_stop(self):
        _, workflow, state, manifest, paths = self.init("document")
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, "task", "skipped", "Not needed", {})
        transition_step(workflow, state, manifest, paths, "image", "skipped", "Not needed", {})
        self.complete_step(workflow, state, manifest, paths, "word", self.make_office_artifacts(paths["submit"]))
        self.assertTrue(state["gates"]["delivery"]["active"])
        self.assertEqual(state["gates"]["delivery"]["status"], "pending")
        with self.assertRaisesRegex(AutoFlowError, "not marked passed|delivery_review"):
            approve_gate(workflow, state, manifest, paths, "delivery", "User accepted the Word delivery")
        self.prepare_delivery_review(workflow, manifest, paths)
        review = gate_review_packet(workflow, state, manifest, paths, "delivery")
        self.assertEqual(review["gate"], "delivery")
        self.assertEqual(len(review["artifacts"]), 2)
        self.assertTrue(review["ready_for_decision"])
        self.assertEqual(review["validation_errors"], [])
        self.assertTrue(Path(review["review_file"]).is_absolute())
        self.assertIn("known limitations or an explicit statement that none remain", review["required_display"])
        approve_gate(workflow, state, manifest, paths, "delivery", "User accepted the Office delivery")
        self.assertEqual(state["status"], "completed")

    def test_plan_stop_requires_requirement_evidence_map(self):
        workflow_path = initialize_run(self.request, self.root / "unmapped", "custom")
        workflow, state, manifest, paths = load_run(workflow_path)
        paths["work_plan"].write_text(COMPLETE_PLAN, encoding="utf-8")
        with self.assertRaisesRegex(AutoFlowError, "at least one requirement"):
            approve_gate(workflow, state, manifest, paths, "plan", "User approved the plan")

    def test_office_acceptance_rejects_stale_validation_report(self):
        _, workflow, state, manifest, paths = self.init("document")
        transition_step(workflow, state, manifest, paths, "task", "skipped", "Not needed", {})
        transition_step(workflow, state, manifest, paths, "image", "skipped", "Not needed", {})
        artifacts = self.make_office_artifacts()
        artifacts["office.document"].write_text("changed after validation", encoding="utf-8")
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, "word", "running", "started", {})
        with self.assertRaisesRegex(AutoFlowError, "SHA-256"):
            transition_step(workflow, state, manifest, paths, "word", "completed", "done", artifacts)

    def test_failed_step_sets_workflow_failed(self):
        _, workflow, state, manifest, paths = self.init("document")
        transition_step(workflow, state, manifest, paths, "task", "running", "started", {})
        transition_step(workflow, state, manifest, paths, "task", "failed", "real execution failed", {})
        self.assertEqual(state["steps"]["task"]["status"], "failed")
        self.assertEqual(state["status"], "failed")

    def test_revision_attempt_budget_requires_diagnosis_before_more_retries(self):
        workflow_path, workflow, state, manifest, paths = self.init("custom")
        workflow["steps"][0]["max_attempts"] = 2
        for attempt in range(2):
            transition_step(workflow, state, manifest, paths, "task", "running", f"attempt {attempt + 1}", {})
            transition_step(workflow, state, manifest, paths, "task", "failed", "repeat failure", {})
        with self.assertRaisesRegex(AutoFlowError, "attempt budget"):
            transition_step(workflow, state, manifest, paths, "task", "running", "unbounded retry", {})

        revise_step(workflow, state, manifest, paths, "task", "Diagnosed repeated failure")
        transition_step(workflow, state, manifest, paths, "task", "running", "new revision", {})
        self.assertEqual(state["steps"]["task"]["revision_attempts"], 1)
        self.assertFalse(state["gates"]["delivery"]["active"])

    def test_video_acceptance_requires_matching_metadata_and_hash(self):
        media = self.make_artifact("demo.mp4", "video-bytes")
        report = self.root / "video-validation.json"
        save_json(
            report,
            {
                "$schema": "autoflow/video-validation/1.0",
                "file": str(media.resolve()),
                "sha256": hash_path(media),
                "metadata": {"duration_seconds": 3.0, "width": 1280, "height": 720, "codec": "h264"},
                "checks": [{"name": "probe", "status": "passed", "evidence": "fixture"}],
                "overall_pass": True,
            },
        )
        validate_video_acceptance({"video.media": media, "video.validation": report})
        media.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(AutoFlowError, "SHA-256"):
            validate_video_acceptance({"video.media": media, "video.validation": report})

    def test_package_acceptance_requires_manifest_checks_and_requirement_ids(self):
        submit_root = self.root / "submit"
        output_folder = submit_root / "delivery"
        output_folder.mkdir(parents=True)
        (output_folder / "report.docx").write_text("report", encoding="utf-8")
        bundle = submit_root / "submit.zip"
        bundle.write_text("archive", encoding="utf-8")
        # The manifest is run metadata: it lives outside submit/, in the run managed area
        plans_dir = self.root / ".autoflow" / "intermediate" / "plans"
        plans_dir.mkdir(parents=True)
        manifest_path = plans_dir / "submit_manifest.json"
        save_json(
            manifest_path,
            {
                "$schema": "autoflow/package-manifest/1.0",
                "output_zip": str(bundle.resolve()),
                "output_folder": str(output_folder.resolve()),
                "files": [
                    {
                        "source": str(bundle),
                        "archive_path": "report.docx",
                        "size": 7,
                        "sha256": "abc",
                        "requirement_ids": ["R1"],
                    }
                ],
                "checks": [{"name": "listing", "status": "passed", "evidence": "fixture"}],
                "overall_pass": True,
            },
        )
        validate_package_acceptance({"package.bundle": bundle, "package.manifest": manifest_path}, submit_root)
        data = load_json(manifest_path)
        data["files"][0]["requirement_ids"] = []
        save_json(manifest_path, data)
        with self.assertRaisesRegex(AutoFlowError, "requirement_ids"):
            validate_package_acceptance({"package.bundle": bundle, "package.manifest": manifest_path}, submit_root)

    def test_package_acceptance_rejects_final_artifacts_outside_submit(self):
        submit_root = self.root / "submit"
        submit_root.mkdir()
        outside_folder = self.root / "outside-delivery"
        outside_folder.mkdir()
        bundle = self.make_artifact("outside.zip", "archive")
        manifest_path = self.root / "outside-manifest.json"
        save_json(manifest_path, {
            "$schema": "autoflow/package-manifest/1.0",
            "output_zip": str(bundle.resolve()),
            "output_folder": str(outside_folder.resolve()),
            "files": [{"archive_path": "report.docx", "sha256": "abc", "requirement_ids": ["R1"]}],
            "checks": [{"name": "listing", "status": "passed"}],
            "overall_pass": True,
        })
        with self.assertRaisesRegex(AutoFlowError, "autoflow/submit"):
            validate_package_acceptance({"package.bundle": bundle, "package.manifest": manifest_path}, submit_root)

    def test_unpacked_terminal_outputs_must_be_below_submit(self):
        submit_root = self.root / "submit"
        submit_root.mkdir()
        workflow = {"steps": [{"id": "word", "module": "office", "format": "word", "needs": []}]}
        step = workflow["steps"][0]
        outside = self.make_artifact("outside.docx", "doc")
        with self.assertRaisesRegex(AutoFlowError, "autoflow/submit"):
            validate_unpacked_final_locations(workflow, step, {"office.document": outside}, submit_root)
        inside = submit_root / "report.docx"
        inside.write_text("doc", encoding="utf-8")
        validate_unpacked_final_locations(workflow, step, {"office.document": inside}, submit_root)

    def test_visual_stop_blocks_word_until_user_approval(self):
        _, workflow, state, manifest, paths = self.init("lab-report")
        task_result = self.make_artifact("task-result.json", "{}")
        self.complete_step(workflow, state, manifest, paths, "task", {"task.result": task_result})
        image_dir = self.root / "images"
        image_dir.mkdir()
        (image_dir / "screen.png").write_bytes(b"png")
        self.complete_step(workflow, state, manifest, paths, "image", {"image.assets": image_dir})
        self.assertEqual(refresh_ready(workflow, state), [])
        self.assertEqual(state["gates"]["visual"]["status"], "pending")
        review = gate_review_packet(workflow, state, manifest, paths, "visual")
        self.assertEqual(review["gate"], "visual")
        self.assertEqual(review["artifacts"][0]["id"], "image.assets")
        self.assertIn("the actual images, rendered slides, or sampled video frames", review["required_display"])
        approve_gate(workflow, state, manifest, paths, "visual", "User approved the displayed screenshots")
        self.assertIn("word", refresh_ready(workflow, state))

    def test_github_candidates_activate_source_stop(self):
        _, workflow, state, manifest, paths = self.init("project-delivery")
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, "source", "running", "searching", {})
        source_plan = {
            "status": "awaiting_user_choice",
            "queries": ["course system servlet jdbc"],
            "candidates": [
                {
                    "rank": rank,
                    "name": name,
                    "repository_url": f"https://github.com/{name}",
                    "revision": revision,
                    "license": "MIT",
                    "scores": {
                        "requirement_fit": 6 - rank,
                        "modification_distance": 4,
                        "stack": 5,
                        "buildability": 4,
                        "maintenance": 4,
                        "license": 5,
                    },
                    "judgment": "Usable fit with a buildable baseline",
                }
                for rank, name, revision in (
                    (1, "owner/repo", "abc123"),
                    (2, "owner/runner-up", "def456"),
                    (3, "owner/third-choice", "ghi789"),
                )
            ],
            "selected_candidate": {},
            "user_choice": {"status": "awaiting_user_choice"},
            "fallback": {"used": False, "reason": ""},
        }
        save_json(paths["source_plan"], source_plan)
        transition_step(
            workflow,
            state,
            manifest,
            paths,
            "source",
            "completed",
            "candidates inspected",
            {"source.plan": paths["source_plan"]},
        )
        self.assertEqual(state["gates"]["source"]["status"], "pending")
        self.assertEqual(refresh_ready(workflow, state), [])
        review = gate_review_packet(workflow, state, manifest, paths, "source")
        self.assertEqual(review["gate"], "source")
        self.assertEqual(len(review["candidates"]), 3)
        self.assertEqual(review["candidates"][0]["revision"], "abc123")
        self.assertTrue(Path(review["review_file"]).is_absolute())

        source_plan.update(
            {
                "status": "selected",
                "selected_candidate": {
                    "name": "owner/repo",
                    "repository_url": "https://github.com/owner/repo",
                    "selected_revision": "abc123",
                    "selection_rationale": "Best requirement fit",
                },
                "user_choice": {"status": "confirmed", "selected_rank": 1},
            }
        )
        save_json(paths["source_plan"], source_plan)
        approve_gate(workflow, state, manifest, paths, "source", "User selected candidate 1")
        self.assertIn("build", refresh_ready(workflow, state))
        self.assertEqual(validate_run(workflow, state, manifest, paths), [])

    def test_direct_route_rejects_unknown_actions_without_creating_state(self):
        payload = route_for_direct("image", "diagram")
        self.assertEqual(payload["execution_mode"], "direct")
        self.assertEqual(payload["stop_gates"], [])
        self.assertFalse(payload["workflow_files_created"])
        with self.assertRaisesRegex(AutoFlowError, "Unknown direct action"):
            route_for_direct("image", "unsupported")

    def test_no_candidate_uses_from_scratch_without_source_approval(self):
        _, workflow, state, manifest, paths = self.init("project-delivery")
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, "source", "running", "searching", {})
        source_plan = {
            "status": "no_suitable_project",
            "queries": ["very specific unsupported stack"],
            "candidates": [],
            "rejected_candidates": [{"repository_url": "https://github.com/owner/repo", "reason": "Wrong stack"}],
            "fallback": {"used": True, "reason": "No candidate satisfies the required stack and license"},
        }
        save_json(paths["source_plan"], source_plan)
        transition_step(
            workflow,
            state,
            manifest,
            paths,
            "source",
            "completed",
            "no suitable source",
            {"source.plan": paths["source_plan"]},
        )
        self.assertEqual(state["gates"]["source"]["status"], "not_applicable")
        self.assertIn("build", refresh_ready(workflow, state))

    def test_missing_artifact_rejects_completion(self):
        _, workflow, state, manifest, paths = self.init("custom")
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, "task", "running", "started", {})
        with self.assertRaises(AutoFlowError):
            transition_step(workflow, state, manifest, paths, "task", "completed", "done", {})

    def test_source_gate_cannot_be_skipped_without_no_candidate_record(self):
        _, workflow, state, _, paths = self.init("project-delivery")
        with self.assertRaises(AutoFlowError):
            set_gate_state(workflow, state, paths, "source", "not_applicable", "skip")

    def test_build_completion_rejects_placeholder_project(self):
        _, workflow, state, manifest, paths = self.init("project-delivery")
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, "source", "running", "searching", {})
        source_plan = {
            "status": "no_suitable_project",
            "queries": ["specific project"],
            "candidates": [],
            "fallback": {"used": True, "reason": "No compatible licensed repository"},
            "search_notes": "Search results did not contain a compatible repository.",
        }
        save_json(paths["source_plan"], source_plan)
        transition_step(
            workflow, state, manifest, paths, "source", "completed", "searched",
            {"source.plan": paths["source_plan"]},
        )
        refresh_ready(workflow, state)
        transition_step(workflow, state, manifest, paths, "build", "running", "building", {})
        project = self.root / "placeholder-project"
        project.mkdir()
        result = self.make_artifact("placeholder-result.json", "{}")
        with self.assertRaisesRegex(AutoFlowError, "empty|README|source_mode"):
            transition_step(
                workflow, state, manifest, paths, "build", "completed", "done",
                {"project.source": project, "task.result": result},
            )

    def test_build_workflow_requires_environment_artifact(self):
        workflow = {
            "$schema": "autoflow/1.0",
            "schema_version": "1.0",
            "steps": [{
                "id": "build", "module": "task", "action": "build", "needs": [],
                "inputs": ["request"], "outputs": ["project.source", "task.result"],
                "validator": "artifacts_exist",
            }],
        }
        with self.assertRaisesRegex(AutoFlowError, "task.environment"):
            validate_workflow_definition(workflow)

    def test_environment_report_accepts_agent_init_evidence(self):
        project = self.root / "agent-init-project"
        runtime = self.root / "agent-init-runtime"
        report_path = self.root / "agent-init-report.json"
        project.mkdir()
        runtime.mkdir()
        save_json(
            report_path,
            {
                "$schema": "autoflow/environment-report/1.0",
                "command": "agent-init",
                "project": str(project.resolve()),
                "runtime_root": str(runtime.resolve()),
                "status": "ready",
                "missing_tools": [],
                "checks": [{"name": "python --version", "status": "passed"}],
            },
        )

        report = validate_environment_report(report_path, project)

        self.assertEqual(report["command"], "agent-init")

    def test_cycle_is_rejected(self):
        workflow_path = initialize_run(self.request, self.root / "cycle", "custom")
        workflow = load_json(workflow_path)
        workflow["steps"][0]["needs"] = ["task"]
        with self.assertRaisesRegex(AutoFlowError, "cannot depend on itself|cycle"):
            validate_workflow_definition(workflow)

    def test_producer_qualified_inputs_are_accepted(self):
        workflow_path = initialize_run(self.request, self.root / "prod-qualified", "custom")
        workflow = load_json(workflow_path)
        workflow["steps"] = [
            {
                "id": "word",
                "module": "office",
                "action": "create",
                "format": "word",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["office.document", "office.validation"],
                "validator": "office_acceptance",
            },
            {
                "id": "ppt",
                "module": "office",
                "action": "create",
                "format": "ppt",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["office.document", "office.validation"],
                "validator": "office_acceptance",
            },
            {
                "id": "package",
                "module": "package",
                "action": "assemble",
                "needs": ["word", "ppt"],
                "inputs": ["word::office.document", "ppt::office.document"],
                "outputs": ["package.bundle", "package.manifest"],
                "validator": "package_acceptance",
            },
        ]
        validate_workflow_definition(workflow)

    def test_producer_qualified_inputs_reject_unknown_producer(self):
        workflow_path = initialize_run(self.request, self.root / "prod-bad", "custom")
        workflow = load_json(workflow_path)
        workflow["steps"] = [
            {
                "id": "word",
                "module": "office",
                "action": "create",
                "format": "word",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["office.document", "office.validation"],
                "validator": "office_acceptance",
            },
            {
                "id": "package",
                "module": "package",
                "action": "assemble",
                "needs": ["word"],
                "inputs": ["mystery::office.document"],
                "outputs": ["package.bundle", "package.manifest"],
                "validator": "package_acceptance",
            },
        ]
        with self.assertRaisesRegex(AutoFlowError, "unknown producer artifact"):
            validate_workflow_definition(workflow)

    def test_producer_qualified_inputs_record_consumers(self):
        workflow = {
            "steps": [
                {
                    "id": "word",
                    "module": "office",
                    "action": "create",
                    "format": "word",
                    "needs": [],
                    "inputs": ["request"],
                    "outputs": ["office.document", "office.validation"],
                    "validator": "office_acceptance",
                },
                {
                    "id": "ppt",
                    "module": "office",
                    "action": "create",
                    "format": "ppt",
                    "needs": [],
                    "inputs": ["request"],
                    "outputs": ["office.document", "office.validation"],
                    "validator": "office_acceptance",
                },
                {
                    "id": "package",
                    "module": "package",
                    "action": "assemble",
                    "needs": ["word", "ppt"],
                    "inputs": ["word::office.document", "ppt::office.document"],
                    "outputs": ["package.bundle", "package.manifest"],
                    "validator": "package_acceptance",
                },
            ]
        }
        manifest = {"artifacts": [], "updated_at": ""}
        step = workflow["steps"][0]
        with tempfile.TemporaryDirectory() as td:
            document = Path(td) / "report.docx"
            document.write_bytes(b"docx-content")
            report = Path(td) / "validation.json"
            report.write_bytes(b"{}")
            register_step_artifacts(
                workflow, manifest, step, {"office.document": document, "office.validation": report}
            )
        records = {f"{item['producer']}::{item['id']}": item for item in manifest["artifacts"]}
        self.assertIn("package", records["word::office.document"]["consumers"])
        self.assertEqual(records["word::office.validation"]["consumers"], [])

    def test_custom_dag_can_sync_before_plan_only(self):
        workflow_path = initialize_run(self.request, self.root / "sync", "custom")
        workflow, state, manifest, paths = load_run(workflow_path)
        workflow["steps"].append(
            {
                "id": "package",
                "module": "package",
                "action": "assemble",
                "needs": ["task"],
                "inputs": ["task.result"],
                "outputs": ["package.bundle", "package.manifest"],
                "validator": "package_acceptance",
            }
        )
        sync_planning_state(workflow, state)
        self.assertEqual(set(state["steps"]), {"task", "package"})
        paths["work_plan"].write_text(COMPLETE_PLAN, encoding="utf-8")
        save_json(
            paths["requirement_map"],
            {
                "$schema": "autoflow/requirement-map/1.0",
                "workflow_id": workflow["workflow_id"],
                "status": "planning",
                "target_tier": "tests-complete",
                "source_files": [str(self.request)],
                "requirements": [
                    {
                        "id": "R1",
                        "description": "Create the custom package output",
                        "required": True,
                        "acceptance": "Package exists",
                        "evidence_artifacts": ["package.bundle", "package.manifest"],
                        "validation": {"status": "pending", "evidence": ""},
                    }
                ],
                "planned_figures": [],
            },
        )
        approve_gate(workflow, state, manifest, paths, "plan", "User approved the custom DAG")
        with self.assertRaises(AutoFlowError):
            sync_planning_state(workflow, state)

    def test_sync_populates_capabilities_for_custom_office_steps(self):
        workflow_path = initialize_run(self.request, self.root / "capabilities", "custom")
        workflow, state, _, _ = load_run(workflow_path)
        workflow["steps"] = [
            {
                "id": "word",
                "module": "office",
                "action": "create",
                "format": "word",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["office.document", "office.validation"],
                "validator": "office_acceptance",
            },
            {
                "id": "ppt",
                "module": "office",
                "action": "create",
                "format": "ppt",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["office.document", "office.validation"],
                "validator": "office_acceptance",
                "gate_after": "visual",
            },
        ]
        sync_planning_state(workflow, state)
        self.assertEqual(workflow["capabilities"]["office"]["backend"], "officecli")
        self.assertEqual(
            workflow["capabilities"]["office"]["status"],
            detect_office_backend()["status"],
        )

    def test_legacy_workflow_is_rejected(self):
        run = self.root / "legacy"
        run.mkdir()
        legacy = run / "workflow.json"
        legacy.write_text(json.dumps({"template_path": "old.docx", "output_docx": "result.docx"}), encoding="utf-8")
        with self.assertRaisesRegex(AutoFlowError, "Legacy workflow detected"):
            load_run(legacy)

    def test_registered_artifact_change_fails_validation(self):
        _, workflow, state, manifest, paths = self.init("custom")
        artifact = paths["submit"] / "result.txt"
        artifact.write_text("v1", encoding="utf-8")
        self.complete_step(workflow, state, manifest, paths, "task", {"task.result": artifact})
        artifact.write_text("v2", encoding="utf-8")
        errors = validate_run(workflow, state, manifest, paths)
        self.assertTrue(any("changed after validation" in error for error in errors))

    def test_office_recipe_discovers_officecli_backend(self):
        backend = detect_office_backend()
        self.assertIn(backend["status"], {"available", "blocked", "missing"})
        self.assertEqual(backend["backend"], "officecli")
        self.assertTrue(Path(backend["engine_script"]).is_file())
        self.assertTrue(Path(backend["validator_script"]).is_file())
        self.assertFalse(backend["external_skill_required"])
        workflow_path = initialize_run(self.request, self.root / "slides", "presentation")
        workflow = load_json(workflow_path)
        self.assertEqual(workflow["capabilities"]["office"]["status"], backend["status"])

    def test_minimax_word_backend_is_available_from_integration_package(self):
        with patch("autoflow_core.load_skill_env", return_value={"WORD_AUTHORING_SKILL": "auto"}):
            backend = detect_office_backend()

        minimax = next(item for item in backend["word_backend_options"] if item["backend"] == "minimaxdocx")
        self.assertIn("integrations", minimax["root"].replace("\\", "/"))
        self.assertEqual(
            backend["word_backend"]["selected"],
            "minimaxdocx" if minimax["status"] == "available" else "officecli",
        )
        self.assertIn("officecli", {item["backend"] for item in backend["word_backend_options"]})

    def test_video_backend_is_local_and_runtime_checked(self):
        backend = detect_video_backend()
        self.assertIn(backend["status"], {"available", "partial", "blocked", "missing"})
        self.assertEqual(backend["backend"], "integrated-video-process")
        self.assertFalse(backend["external_skill_required"])
        self.assertTrue(Path(backend["script"]).is_file())

    def test_image_backend_routes_actions_without_external_skill_fallback(self):
        backend = detect_image_backend(["diagram", "chart"])
        self.assertIn(backend["status"], {"available", "partial", "blocked", "missing"})
        self.assertEqual(backend["backend"], "integrated-image-assets")
        self.assertFalse(backend["external_skill_required"])
        self.assertIn("diagram", backend["actions"])
        self.assertIn("chart", backend["actions"])
        self.assertTrue(all(Path(path).is_file() for path in backend["actions"]["diagram"]["files"]))

    def test_image_diagram_route_exposes_local_renderer_files(self):
        workflow_path = initialize_run(self.request, self.root / "diagram-route", "custom")
        workflow, state, _, _ = load_run(workflow_path)
        workflow["steps"] = [
            {
                "id": "diagram",
                "module": "image",
                "action": "diagram",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["image.assets"],
                "validator": "artifacts_exist",
                "gate_after": "visual",
            }
        ]
        sync_planning_state(workflow, state)
        route = route_for_workflow(workflow, state, "diagram")
        self.assertIn("image", route["capability_names"])
        self.assertTrue(all(Path(path).is_file() for path in route["capability_files"]))

    def test_document_recipe_routes_office_word_with_officecli_capability(self):
        workflow_path = initialize_run(self.request, self.root / "word", "document")
        workflow = load_json(workflow_path)
        word_step = next(step for step in workflow["steps"] if step["id"] == "word")
        self.assertEqual(word_step["module"], "office")
        self.assertEqual(word_step["format"], "word")
        self.assertEqual(word_step["validator"], "office_acceptance")
        self.assertEqual(
            workflow["capabilities"]["office"]["status"],
            detect_office_backend()["status"],
        )

    def test_image_route_reports_only_selected_action_capability(self):
        steps = [
            {
                "id": "capture",
                "module": "image",
                "action": "capture",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["capture.result"],
                "validator": "artifacts_exist",
            },
            {
                "id": "ai",
                "module": "image",
                "action": "ai",
                "needs": [],
                "inputs": ["request"],
                "outputs": ["ai.result"],
                "validator": "artifacts_exist",
            },
        ]
        workflow = {
            "$schema": "autoflow/1.0",
            "schema_version": "1.0",
            "workflow_id": "image-route-isolation",
            "recipe": "custom",
            "steps": steps,
            "capabilities": {
                "image": {
                    "status": "blocked",
                    "backend": "integrated-image-assets",
                    "actions": {
                        "capture": {"status": "available", "message": "ready", "files": []},
                        "ai": {"status": "blocked", "message": "missing credentials", "files": []},
                    },
                }
            },
        }
        state = {"steps": {"capture": {"status": "pending"}, "ai": {"status": "pending"}}}

        capture_route = route_for_workflow(workflow, state, "capture")
        ai_route = route_for_workflow(workflow, state, "ai")

        self.assertEqual(capture_route["capabilities"]["image"]["status"], "available")
        self.assertEqual(set(capture_route["capabilities"]["image"]["actions"]), {"capture"})
        self.assertEqual(ai_route["capabilities"]["image"]["status"], "blocked")
        self.assertEqual(set(ai_route["capabilities"]["image"]["actions"]), {"ai"})

    def test_image_capability_accepts_colon_delimited_env_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env").write_text(
                "BASEURL:https://images.example.test\nAPIKEY:non-placeholder-key\n",
                encoding="utf-8",
            )

            configured, detail = _image_env_status(root)

            self.assertTrue(configured)
            self.assertEqual(detail, "configured")

    def test_hash_path_ignores_maven_target_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "src").mkdir()
            (root / "src" / "App.java").write_text("class App {}", encoding="utf-8")
            initial = hash_path(root)
            (root / "target").mkdir()
            (root / "target" / "App.class").write_bytes(b"compiled")

            self.assertEqual(hash_path(root), initial)

    def test_integration_catalog_audits_every_checked_in_integration(self):
        catalog = integration_catalog()
        self.assertEqual(
            {item["name"] for item in catalog},
            {"impeccable", "minimax-docx", "nature-figure", "officecli"},
        )
        self.assertTrue(all(item["status"] == "available" for item in catalog))
        for item in catalog:
            self.assertIn(item["type"], {"tool", "knowledge-only"})
            self.assertGreaterEqual(len(item["capabilities"]), 1)
        self.assertEqual({item["name"] for item in catalog if item["role"] == "engine"}, {"officecli"})
        self.assertTrue(all(item["check_status"] == "available" for item in catalog))

    def _make_manifest(self, directory: Path, name: str, pkg_type: str, check: bool = True) -> None:
        manifest = {
            "$schema": "autoflow/integration-manifest/2.0",
            "name": name,
            "type": pkg_type,
            "capabilities": {"demo-cap": {"description": "demo"}},
            "upstream": "https://example.com/repo",
            "revision": "abc123",
            "license": "MIT",
            "self_contained": True,
            "external_user_skill_required": False,
            "source_checkout_required": False,
        }
        if check:
            manifest["check"] = {"entry": "scripts/check.py", "runtime": "python"}
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def test_integration_catalog_reports_missing_and_invalid_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nomanifest").mkdir()
            (root / "badmanifest").mkdir()
            (root / "badmanifest" / "manifest.json").write_text("{not json", encoding="utf-8")
            with patch("autoflow_core._integration_manifest_root", return_value=root):
                catalog = integration_catalog()
        by_name = {item["name"]: item for item in catalog}
        self.assertEqual(by_name["nomanifest"]["status"], "missing_manifest")
        self.assertEqual(by_name["badmanifest"]["status"], "invalid_manifest")

    def test_integration_catalog_runs_package_check_and_knowledge_only_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool_pkg = root / "toolpkg"
            tool_pkg.mkdir()
            self._make_manifest(tool_pkg, "toolpkg", "tool")
            (tool_pkg / "scripts").mkdir()
            (tool_pkg / "scripts" / "check.py").write_text(
                'import json; print(json.dumps({"status": "missing", "version": None, "error": "dep not installed"}))',
                encoding="utf-8",
            )
            know_pkg = root / "knowledge"
            know_pkg.mkdir()
            self._make_manifest(know_pkg, "knowledge", "knowledge-only", check=False)
            with patch("autoflow_core._integration_manifest_root", return_value=root):
                catalog = integration_catalog()
            by_name = {item["name"]: item for item in catalog}
            self.assertEqual(by_name["toolpkg"]["status"], "missing")
            self.assertEqual(by_name["toolpkg"]["check_status"], "missing")
            self.assertIn("dep not installed", by_name["toolpkg"]["check_message"])
            self.assertEqual(by_name["knowledge"]["status"], "missing")  # no SKILL.md yet
            (know_pkg / "SKILL.md").write_text("# knowledge\n", encoding="utf-8")
            with patch("autoflow_core._integration_manifest_root", return_value=root):
                catalog = integration_catalog()
            by_name = {item["name"]: item for item in catalog}
            self.assertEqual(by_name["knowledge"]["status"], "available")
            self.assertEqual(by_name["knowledge"]["type"], "knowledge-only")

    def test_auto_recipe_recommends_project_report_and_slides_transparently(self):
        selection = recommend_recipe("学生管理系统源码、论文和答辩PPT")
        self.assertEqual(selection["selected"], "project-report-and-slides")
        self.assertEqual(selection["mode"], "deterministic_recommendation")
        self.assertTrue(selection["signals"]["project"])
        self.assertTrue(selection["signals"]["document"])
        self.assertTrue(selection["signals"]["slides"])

    def test_auto_recipe_keeps_unknown_requests_custom(self):
        selection = recommend_recipe("请帮我分析一段没有交付格式说明的材料")
        self.assertEqual(selection["selected"], "custom")
        self.assertIn("custom DAG", selection["reason"])

    def test_auto_recipe_routes_video_to_verified_video_delivery(self):
        selection = recommend_recipe("请制作一个真实演示录屏视频并提交可播放文件")
        self.assertEqual(selection["selected"], "video-delivery")

    def test_route_for_build_step_returns_module_and_capability_paths(self):
        workflow_path = initialize_run(self.request, self.root / "route", "project-delivery")
        workflow, state, _, _ = load_run(workflow_path)
        route = route_for_workflow(workflow, state, "build", compact=False)
        self.assertEqual(route["step"]["id"], "build")
        self.assertTrue(route["module_file"].endswith("modules\\task.md"))
        self.assertTrue(all(Path(path).is_file() for path in route["skill_files"]))
        self.assertTrue(all(Path(path).is_file() for path in route["capability_files"]))

    def test_compact_route_skips_optional_skill_overlays(self):
        _, workflow, state, _, _ = self.init("project-delivery")
        route = route_for_workflow(workflow, state, "build")
        self.assertEqual(route["mode"], "compact")
        self.assertEqual(route["global_skill_names"], [])
        self.assertTrue(all(Path(path).is_file() for path in route["skill_files"]))

    def test_revise_invalidates_target_downstream_artifacts_and_delivery(self):
        workflow_path = initialize_run(self.request, self.root / "revision", "custom")
        workflow, state, manifest, paths = load_run(workflow_path)
        workflow["steps"] = [
            {"id": "task", "module": "task", "action": "execute", "needs": [], "inputs": ["request"], "outputs": ["task.result"], "validator": "artifacts_exist"},
            {"id": "downstream", "module": "task", "action": "compute", "needs": ["task"], "inputs": ["task.result"], "outputs": ["downstream.result"], "validator": "artifacts_exist"},
        ]
        sync_planning_state(workflow, state)
        paths["work_plan"].write_text(COMPLETE_PLAN, encoding="utf-8")
        save_json(paths["requirement_map"], {
            "$schema": "autoflow/requirement-map/1.0", "workflow_id": workflow["workflow_id"], "status": "planning",
            "target_tier": "revision-test", "source_files": [str(self.request)],
            "requirements": [{"id": "R1", "description": "Outputs", "required": True, "acceptance": "Both exist", "evidence_artifacts": ["task.result", "downstream.result"], "validation": {"status": "passed"}}],
            "planned_figures": [],
        })
        approve_gate(workflow, state, manifest, paths, "plan", "User approved")
        self.complete_step(workflow, state, manifest, paths, "task", {"task.result": self.make_artifact("task.json", "{}")})
        downstream = paths["submit"] / "downstream.txt"
        downstream.write_text("result", encoding="utf-8")
        self.complete_step(workflow, state, manifest, paths, "downstream", {"downstream.result": downstream})
        affected = revise_step(workflow, state, manifest, paths, "task", "Update implementation")
        self.assertEqual(affected, ["task", "downstream"])
        self.assertEqual(state["steps"]["task"]["status"], "ready")
        self.assertEqual(state["steps"]["downstream"]["status"], "pending")
        self.assertEqual(manifest["artifacts"], [])
        self.assertEqual(len(manifest["artifact_history"]), 2)
        self.assertEqual(state["gates"]["delivery"]["status"], "pending")
        self.assertFalse(state["gates"]["delivery"]["active"])

    def test_revise_rejects_delivered_workflow(self):
        _, workflow, state, manifest, paths = self.init("custom")
        done = paths["submit"] / "done.txt"
        done.write_text("done", encoding="utf-8")
        self.complete_step(workflow, state, manifest, paths, "task", {"task.result": done})
        state["status"] = "completed"
        state["gates"]["delivery"]["status"] = "approved"
        with self.assertRaisesRegex(AutoFlowError, "immutable"):
            revise_step(workflow, state, manifest, paths, "task", "Too late")

    def test_environment_report_requires_verified_matching_external_runtime(self):
        project = self.root / "environment-project"
        runtime = self.root / "environment-runtime"
        project.mkdir()
        runtime.mkdir()
        report_path = self.root / "environment.json"
        payload = {
            "$schema": "autoflow/environment-report/1.0",
            "command": "detect",
            "project": str(project),
            "runtime_root": str(runtime),
            "status": "ready",
            "project_kinds": ["python"],
            "missing_tools": [],
            "checks": [],
        }
        save_json(report_path, payload)
        with self.assertRaisesRegex(AutoFlowError, "must be agent-init"):
            validate_environment_report(report_path, project)
        payload["command"] = "agent-init"
        payload["checks"] = [{"name": "python_dependency_consistency", "status": "passed"}]
        save_json(report_path, payload)
        self.assertEqual(validate_environment_report(report_path, project)["status"], "ready")
        payload["project"] = str(self.root / "different-project")
        save_json(report_path, payload)
        with self.assertRaisesRegex(AutoFlowError, "does not match"):
            validate_environment_report(report_path, project)

    def test_impeccable_is_an_integrated_offline_frontend_backend(self):
        backend = detect_impeccable_backend()
        self.assertEqual(backend["status"], "available")
        self.assertEqual(backend["backend"], "integrated-impeccable")
        self.assertFalse(backend["network_update_check"])
        self.assertTrue(Path(backend["skill_file"]).is_file())
        package = Path(backend["integration_root"])
        self.assertTrue((package / "scripts" / "impeccable_adapter.mjs").is_file())


if __name__ == "__main__":
    unittest.main()
