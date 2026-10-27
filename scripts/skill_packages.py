"""Install and enumerate locally managed GitHub Skill repositories."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


SLUG_RE = re.compile(r"^[a-z0-9-]{1,100}$")
PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def canonical_github_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url.strip())
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.query or parsed.fragment or len(parts) != 2:
        raise ValueError("Use a GitHub HTTPS clone URL: https://github.com/owner/repo.git")
    owner, repo = parts
    repo = repo.removesuffix(".git")
    if not owner or not repo or owner in {".", ".."} or repo in {".", ".."} or not all(PART_RE.fullmatch(p) for p in (owner, repo)):
        raise ValueError("Invalid GitHub owner or repository")
    slug = f"{owner}--{repo}".lower()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("Repository name is too long or unsupported")
    return f"https://github.com/{owner}/{repo}.git", slug


def _skill_files(source: Path) -> list[Path]:
    root_files = [*source.glob("SKILL.md"), *source.glob("skills.md")]
    candidates = root_files or [*source.glob("skills/*/SKILL.md"), *source.glob("skills/*/skills.md")]
    return sorted(path for path in candidates if path.is_file() and not path.is_symlink()
                  and path.resolve().is_relative_to(source.resolve()))


def installed_skills(root: Path) -> list[dict]:
    base = root / "user_skills"
    if not base.is_dir():
        return []
    items = []
    for directory in sorted(base.iterdir()):
        if not directory.is_dir() or directory.is_symlink() or not SLUG_RE.fullmatch(directory.name):
            continue
        try:
            metadata = json.loads((directory / "install.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        source = directory / "source"
        files = _skill_files(source) if source.is_dir() else []
        items.append({"id": f"github:{directory.name}", "url": metadata.get("url", ""),
                      "revision": metadata.get("revision", ""), "skill_files": [str(p.resolve()) for p in files],
                      "status": "available" if len(files) == 1 else ("multiple" if files else "missing")})
    return items


def install_skill(root: Path, url: str) -> dict:
    canonical, slug = canonical_github_url(url)
    base = root / "user_skills"
    base.mkdir(exist_ok=True)
    target = base / slug
    if target.exists():
        raise ValueError("Skill is already installed")
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=base))
    try:
        git_env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_COUNT": "0"}
        try:
            proc = subprocess.run(["git", "-c", "protocol.file.allow=never", "-c", "protocol.ext.allow=never",
                                   "-c", "http.followRedirects=false", "-c", f"core.hooksPath={staging / '.no-hooks'}",
                                   "clone", "--depth", "1", "--", canonical, str(staging / "source")],
                                  capture_output=True, text=True, timeout=120, check=False, env=git_env)
        except FileNotFoundError as exc:
            raise ValueError("Git is not installed") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("GitHub clone timed out") from exc
        if proc.returncode:
            raise ValueError("GitHub clone failed; check the URL, network access and repository visibility")
        source = staging / "source"
        files = _skill_files(source)
        if not files:
            raise ValueError("Repository must contain SKILL.md or skills.md at its root or under skills/<name>/")
        try:
            revision = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"],
                                      capture_output=True, text=True, timeout=10, check=True, env=git_env).stdout.strip()
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError("Could not verify cloned revision") from exc
        (staging / "install.json").write_text(json.dumps({"url": canonical, "revision": revision}) + "\n", encoding="utf-8")
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return next(item for item in installed_skills(root) if item["id"] == f"github:{slug}")


def delete_skill(root: Path, skill_id: str) -> None:
    if not skill_id.startswith("github:") or not SLUG_RE.fullmatch(skill_id[7:]):
        raise ValueError("Only managed GitHub skills can be removed")
    base = (root / "user_skills").resolve()
    target = base / skill_id[7:]
    if target.is_symlink() or not target.is_dir() or not (target / "install.json").is_file() or target.resolve().parent != base:
        raise ValueError("Managed skill not found")
    shutil.rmtree(target)
