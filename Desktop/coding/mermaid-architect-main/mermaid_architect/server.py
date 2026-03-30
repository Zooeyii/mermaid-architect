"""
HTTP Server and API handlers.
"""

import json
import time
import mimetypes
import webbrowser
from pathlib import Path

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from urllib.parse import parse_qs, unquote, urlparse

from threading import Lock


from mermaid_architect.models import (
    json_dump,
    node_report,
    ready_report,
    next_report,
    progress_report,
    analysis_report,
)

from mermaid_architect.parser import load_source, load_merged_graph

from mermaid_architect.io import write_normalized_graph

def build_http_payload(handler, source_dir):
    parsed = urlparse(handler.path)
    path = parsed.path.rstrip("/") or "/"
    query = parse_qs(parsed.query)
    source = query.get("path", [source_dir])[0]
    graph = load_source(source)

    if handler.command == "GET" and path == "/health":
        return 200, {"status": "ok", "port": handler.server.server_port, "source": source}

    if handler.command == "GET" and path == "/summary":
        return 200, {"summary": graph.full_summary()}

    if handler.command == "GET" and path == "/ready":
        return 200, json.loads(ready_report(graph))

    if handler.command == "GET" and path == "/progress":
        return 200, json.loads(progress_report(graph))

    if handler.command == "GET" and path == "/analyze":
        return 200, json.loads(analysis_report(graph))

    if handler.command == "GET" and path == "/validate":
        issues = graph.validate_issues()
        return 200, {"ok": len(issues) == 0, "issues": issues}

    if handler.command == "POST" and path == "/normalize":
        if not Path(source).is_dir():
            return 400, {"error": "normalize requires a directory source"}
        write_normalized_graph(source, graph)
        return 200, graph.to_object_model()

    if handler.command == "GET" and path.startswith("/node/"):
        node_id = unquote(path.split("/node/", 1)[1])
        return 200, json.loads(node_report(graph, node_id))

    if handler.command == "GET" and path.startswith("/next/"):
        node_id = unquote(path.split("/next/", 1)[1])
        return 200, json.loads(next_report(graph, node_id))

    return 404, {"error": f"unknown route: {path}"}


def serve(source_dir, port=5173, api_only=False, ui_dir=None):
    """Start HTTP server with graph API + optional static UI."""

    claim_lock = Lock()

    # Determine UI directory (default to graph-ui/dist relative to this script)
    if ui_dir is None:
        skill_dir = Path(__file__).parent.parent
        ui_dir = skill_dir / "graph-ui" / "dist"

    ui_path = Path(ui_dir) if api_only else None

    class Handler(BaseHTTPRequestHandler):
        def _write_json(self, status_code, payload):
            body = json_dump(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, rel_path):
            """Serve static files from UI directory."""
            if not ui_path or not ui_path.exists():
                self.send_error(404, "UI not found")
                return

            file_path = ui_path / rel_path.lstrip("/")
            if not file_path.exists() or not file_path.is_file():
                # SPA fallback to index.html
                file_path = ui_path / "index.html"
                if not file_path.exists():
                    self.send_error(404, "File not found")
                    return

            # Determine content type
            content_type, _ = mimetypes.guess_type(str(file_path))
            content_type = content_type or "application/octet-stream"

            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            graph_dir = query.get("dir", [source_dir])[0]

            # Health check
            if path == "/health":
                self._write_json(200, {"ok": True, "port": self.server.server_port})
                return

            # Graph API for visualization UI
            if path == "/api/graph":
                try:
                    graph = load_merged_graph(graph_dir)
                    self._write_json(200, {"ok": True, "graph": graph})
                except Exception as e:
                    self._write_json(500, {"error": str(e)})
                return

            # Evolution log
            if path == "/api/evolution":
                log_path = Path(graph_dir) / "evolution-log.json"
                if not log_path.exists():
                    self._write_json(200, {"applied": [], "pending": [], "history": []})
                else:
                    try:
                        log = json.loads(log_path.read_text(encoding="utf-8"))
                        self._write_json(200, log)
                    except Exception as e:
                        self._write_json(500, {"error": str(e)})
                return

            # SSE for real-time updates
            if path == "/api/graph/sse":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()

                graph_file = Path(graph_dir) / "graph.json"
                last_mtime = graph_file.stat().st_mtime if graph_file.exists() else 0

                try:
                    while True:
                        time.sleep(1)
                        if graph_file.exists():
                            current_mtime = graph_file.stat().st_mtime
                            if current_mtime != last_mtime:
                                last_mtime = current_mtime
                                try:
                                    graph = load_merged_graph(graph_dir)
                                    data = json.dumps({"graph": graph})
                                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                                except Exception:
                                    pass
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            # Legacy API endpoints
            try:
                # Temporarily attach path for legacy handler
                self._graph_dir = graph_dir
                status_code, payload = build_http_payload(self, graph_dir)
                self._write_json(status_code, payload)
            except Exception as error:
                self._write_json(500, {"error": str(error)})

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/")
            query = parse_qs(parsed.query)
            graph_dir = query.get("path", [source_dir])[0]

            if path.startswith("/claim/"):
                node_id = unquote(path.split("/claim/", 1)[1])
                try:
                    content_len = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_len) if content_len > 0 else b"{}"
                    payload = json.loads(body.decode("utf-8"))
                    session = payload.get("session")

                    if not session:
                        self._write_json(400, {"error": "session is required"})
                        return

                    with claim_lock:
                        graph = load_source(graph_dir)
                        node = graph.get_node(node_id)

                        if not node:
                            self._write_json(404, {"error": f"node not found: {node_id}"})
                            return

                        if node.session:
                            self._write_json(409, {"error": "already claimed", "session": node.session})
                            return

                        if not graph.can_execute(node_id):
                            blockers = [b.id for b in graph.blockers(node_id)]
                            self._write_json(400, {"error": "not ready", "blockers": blockers})
                            return

                        node.session = session
                        node.status = "doing"
                        write_normalized_graph(graph_dir, graph)

                        self._write_json(200, {"ok": True, "node": node.to_dict()})
                except Exception as error:
                    self._write_json(500, {"error": str(error)})
                return

            try:
                self._graph_dir = graph_dir
                status_code, payload = build_http_payload(self, graph_dir)
                self._write_json(status_code, payload)
            except Exception as error:
                self._write_json(500, {"error": str(error)})

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)

    # Auto-open browser (only for full mode)
    if not api_only:
        url = f"http://127.0.0.1:{port}"
        print(f"DAG Visualization: {url}")
        print(f"Source: {source_dir}")
        try:
            webbrowser.open(url)
        except Exception:
            pass

    print(f"Server {'API' if api_only else 'UI+API'} listening on http://127.0.0.1:{port}")
    print(f"  Graph API:   GET /api/graph?dir={source_dir}")
    print(f"  SSE:         GET /api/graph/sse?dir={source_dir}")
    if not api_only:
        print(f"  UI:          http://127.0.0.1:{port}/")
        print(f"  UI files:    {ui_path}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
