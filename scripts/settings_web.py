"""Loopback-only settings UI for AutoFlow."""

from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from autoflow_core import detect_office_backend, integration_catalog
from settings_config import public_settings, update_settings
from skill_packages import delete_skill, install_skill, installed_skills


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web"
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


def make_handler(root: Path, token: str):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _allowed(self) -> bool:
            host = self.headers.get("Host", "")
            return host == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self) -> None:
            if not self._allowed():
                self._json(403, {"error": "Invalid host"})
                return
            if self.path == "/api/state":
                self._json(200, {"settings": public_settings(root), "skills": installed_skills(root),
                                 "integrations": integration_catalog(), "office": detect_office_backend(), "csrf": token})
                return
            asset = ASSETS.get(self.path)
            if not asset:
                self._json(404, {"error": "Not found"})
                return
            data = (STATIC / asset[0]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", asset[1])
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self._allowed() or self.headers.get("Origin") != origin or not secrets.compare_digest(self.headers.get("X-CSRF-Token", ""), token):
                self._json(403, {"error": "Request rejected"})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self._json(415, {"error": "Expected JSON"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("Request size is invalid")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Expected an object")
                if self.path == "/api/settings":
                    updates = data.get("values")
                    if not isinstance(updates, dict):
                        raise ValueError("Expected settings values")
                    selected = updates.get("WORD_AUTHORING_SKILL", "")
                    if selected.startswith("github:") and not any(item["id"] == selected and item["status"] == "available" for item in installed_skills(root)):
                        raise ValueError("Selected Word skill is not installed")
                    update_settings(root, updates)
                elif self.path == "/api/skills/install":
                    install_skill(root, data.get("url", ""))
                elif self.path == "/api/skills/delete":
                    skill_id = data.get("id", "")
                    if public_settings(root)["values"]["WORD_AUTHORING_SKILL"] == skill_id:
                        raise ValueError("Select a different Word skill before deleting this one")
                    delete_skill(root, skill_id)
                else:
                    self._json(404, {"error": "Not found"})
                    return
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            except OSError:
                self._json(500, {"error": "Local settings operation failed"})
                return
            self._json(200, {"ok": True})

        def log_message(self, format: str, *args) -> None:
            pass  # Do not log request bodies or credentials.

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local AutoFlow settings")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ROOT, secrets.token_urlsafe(32)))
    print(f"AutoFlow settings: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
