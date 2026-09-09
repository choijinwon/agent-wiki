from __future__ import annotations

import argparse
import json
import mimetypes
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .config import Settings
from .mcp_server import build_agent

STATIC_DIR = Path(__file__).with_name("static")


class KnowledgeHandler(BaseHTTPRequestHandler):
    server_version = "KnowledgeAgent/0.1"

    @property
    def agent(self):
        return self.server.agent  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin == "null" or origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 5_000_000:
            raise ValueError("request body is too large (maximum 5 MB)")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _static(self, name: str) -> None:
        safe_name = "index.html" if name in {"", "/"} else unquote(name).lstrip("/")
        path = (STATIC_DIR / safe_name).resolve()
        if STATIC_DIR.resolve() not in path.parents and path != STATIC_DIR.resolve():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json({"status": "ok", "stats": self.agent.store.stats(), "llm": self.agent.generator.enabled})
        elif path == "/api/documents":
            self._json({"documents": self.agent.store.list_documents()})
        elif path.startswith("/api/"):
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        else:
            self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/documents":
                document = self.agent.store.add_document(
                    title=str(body.get("title", "")),
                    content=str(body.get("content", "")),
                    source=str(body.get("source", "manual")),
                )
                self._json({"document": document}, HTTPStatus.CREATED)
            elif path == "/api/search":
                results = self.agent.store.search(str(body.get("query", "")), int(body.get("limit", 5)))
                self._json({"results": [item.to_dict() for item in results]})
            elif path == "/api/chat":
                self._json(self.agent.ask(str(body.get("question", "")), int(body.get("top_k", 5))))
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception:
            traceback.print_exc()
            self._json({"error": "internal server error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        prefix = "/api/documents/"
        if not path.startswith(prefix):
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        document_id = unquote(path[len(prefix) :])
        if self.agent.store.delete_document(document_id):
            self._json({"deleted": document_id})
        else:
            self._json({"error": "document not found"}, HTTPStatus.NOT_FOUND)


class KnowledgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], settings: Settings):
        super().__init__(address, KnowledgeHandler)
        self.agent = build_agent(settings)


def main() -> None:
    defaults = Settings.from_env()
    parser = argparse.ArgumentParser(description="Run the Knowledge Agent web application")
    parser.add_argument("--host", default=defaults.host)
    parser.add_argument("--port", type=int, default=defaults.port)
    args = parser.parse_args()
    server = KnowledgeServer((args.host, args.port), defaults)
    print(f"Knowledge Agent: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
