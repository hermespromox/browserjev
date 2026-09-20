from __future__ import annotations

import asyncio
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from browserjev import JavaScriptRequired, TransportError, UnsafeURLError  # noqa: E402
from browserjev.decisions import JevError  # noqa: E402
from browserjev.web_api import classify_analysis_payload  # noqa: E402

MAX_BODY_BYTES = 32_768


def _normalized_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _origin_is_allowed(self) -> bool:
        origin = self.headers.get("Origin", "")
        configured = os.getenv("SITE_URL", "").rstrip("/")
        if configured:
            return _normalized_origin(origin) == _normalized_origin(configured)
        if os.getenv("VERCEL"):
            host = self.headers.get("Host", "")
            return bool(origin and host and _normalized_origin(origin) == f"https://{host}")
        if not origin:
            return True
        parsed_origin = urlsplit(origin)
        return parsed_origin.scheme == "http" and parsed_origin.hostname in {
            "localhost",
            "127.0.0.1",
        }

    def do_POST(self) -> None:  # noqa: N802
        if not self._origin_is_allowed():
            self._send_json(403, {"error": "Origine de requête refusée."})
            return

        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send_json(415, {"error": "Le corps doit être envoyé en JSON."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "Taille de requête invalide."})
            return
        if content_length <= 0 or content_length > MAX_BODY_BYTES:
            self._send_json(413, {"error": "La requête est vide ou trop volumineuse."})
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "Le JSON envoyé est invalide."})
            return

        api_key = os.getenv("TYPESAFE_API_KEY")
        if not api_key:
            self._send_json(503, {"error": "Le service Jev n’est pas encore configuré."})
            return

        try:
            result = asyncio.run(classify_analysis_payload(payload, api_key=api_key))
        except ValidationError as exc:
            details = [
                {"field": ".".join(str(part) for part in error["loc"]), "message": error["msg"]}
                for error in exc.errors(include_url=False, include_input=False)
            ]
            self._send_json(
                400,
                {
                    "error": "Vérifiez le domaine et les paramètres des questions.",
                    "details": details,
                },
            )
        except UnsafeURLError as exc:
            self._send_json(400, {"error": str(exc)})
        except JavaScriptRequired:
            self._send_json(
                422,
                {"error": "Ce site nécessite JavaScript et ne peut pas être lu par ce MVP."},
            )
        except TransportError:
            self._send_json(502, {"error": "Le site n’a pas pu être lu correctement."})
        except JevError:
            self._send_json(502, {"error": "Jev n’a pas pu produire de réponse."})
        except Exception as exc:  # pragma: no cover - final production boundary
            print(f"analysis failed: {type(exc).__name__}", file=sys.stderr)
            self._send_json(500, {"error": "L’analyse a échoué de façon inattendue."})
        else:
            self._send_json(200, result.model_dump(mode="json"))

    def do_GET(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "Utilisez POST pour lancer une analyse."})

    def log_message(self, format: str, *args: object) -> None:
        return
