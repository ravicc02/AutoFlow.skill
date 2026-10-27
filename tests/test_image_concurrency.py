import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_images


RESOLUTIONS = {
    "2k_16_9": "2560x1440",
    "4k_16_9": "3840x2160",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Probe image-generation concurrency for 2K/4K 16:9 outputs.")
    parser.add_argument("--output-dir", default="concurrency_probe", help="Directory for probe images and report.")
    parser.add_argument("--workers", default="50,40,32,24,16,12,8,6,4,2,1")
    parser.add_argument("--count", type=int, default=4, help="Images per probe run.")
    parser.add_argument("--resolutions", default="2k_16_9,4k_16_9")
    parser.add_argument("--prompt", default="Realistic low-density terminal screenshot with a short command output, no annotations.")
    parser.add_argument("--dry-run", action="store_true", help="Validate generated configs without calling the image API.")
    return parser.parse_args()


def make_config(output_dir: Path, resolution: str, workers: int, count: int, prompt: str):
    images = [{"name": f"probe_{i + 1:02d}", "mode": "screenshot_strict", "prompt": prompt} for i in range(count)]
    return {
        "total_count": count,
        "resolution": resolution,
        "output_dir": str(output_dir),
        "max_workers": workers,
        "max_retries": 1,
        "retry_delay": 1,
        "image_policy": {
            "default_mode": "screenshot_strict",
            "auto_append_negative": True,
            "fail_on_prompt_risk": True,
            "forbidden_terms": ["poster", "callout", "annotation", "flowchart", "diagram"],
            "ui_density": "low_information_density",
            "crop_browser_chrome": True,
            "forbid_localhost_or_dev_url": True,
        },
        "global_prompt": "",
        "images": images,
    }


def run_probe(config_path: Path, dry_run: bool):
    if dry_run:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return {"success": True, "dry_run": True, "attempted": config["total_count"], "succeeded": 0, "failed": 0}
    started = time.time()
    results = generate_images.generate_from_config(str(config_path))
    succeeded = sum(1 for item in results if item.get("success"))
    failed = sum(1 for item in results if not item.get("success"))
    errors = sorted({item.get("error") for item in results if item.get("error")})
    return {
        "success": failed == 0 and succeeded == len(results),
        "dry_run": False,
        "attempted": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "errors": errors,
        "seconds": round(time.time() - started, 2),
    }


def main():
    args = parse_args()
    output_root = Path(args.output_dir).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    workers = [int(item.strip()) for item in args.workers.split(",") if item.strip()]
    resolution_keys = [item.strip() for item in args.resolutions.split(",") if item.strip()]
    report = {"probes": [], "recommended": {}}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for key in resolution_keys:
            resolution = RESOLUTIONS.get(key, key)
            recommended = None
            for worker_count in workers:
                run_dir = output_root / key / f"workers_{worker_count}"
                config = make_config(run_dir, resolution, worker_count, args.count, args.prompt)
                config_path = tmp_dir / f"{key}_{worker_count}.json"
                config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
                try:
                    result = run_probe(config_path, args.dry_run)
                except Exception as exc:
                    result = {"success": False, "error": str(exc), "dry_run": args.dry_run}
                result.update({"resolution_key": key, "resolution": resolution, "workers": worker_count})
                report["probes"].append(result)
                print(json.dumps(result, ensure_ascii=False))
                if result.get("success"):
                    recommended = worker_count
                    break
            report["recommended"][key] = recommended

    report_path = output_root / "image_concurrency_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Concurrency report written: {report_path}")
    if any(value is None for value in report["recommended"].values()):
        raise SystemExit("No successful concurrency level found for one or more resolutions.")


if __name__ == "__main__":
    main()
