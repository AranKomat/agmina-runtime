"""Forward a bounded local R4 test stream while injecting declared response faults.

This proxy is intentionally localhost-only and has no retry behavior. It is for comparing a real
provider path with the deterministic fault wrapper; it is not a production gateway.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "AgminaR4Proxy/1"

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler hook
        proxy = self.server.proxy_state
        length = int(self.headers.get("Content-Length", "-1"))
        if length < 0 or length > proxy.max_body_bytes:
            self.send_error(413, "bounded request body required")
            return
        body = self.rfile.read(length)
        request_id = self.headers.get("X-Agmina-Request-ID")
        drop = proxy.drop_remaining > 0
        if drop:
            proxy.drop_remaining -= 1
        started = time.monotonic()
        record = {"request_id": request_id, "body_bytes": len(body), "drop": drop}
        try:
            headers = {
                key: value for key, value in self.headers.items()
                if key.lower() not in {"host", "content-length", "connection"}
            }
            with httpx.Client(timeout=proxy.timeout_s, follow_redirects=False, trust_env=False) as client:
                response = client.post(proxy.upstream, content=body, headers=headers)
            record.update({"upstream_status": response.status_code, "upstream_bytes": len(response.content)})
            try:
                upstream_json = response.json()
            except ValueError:
                upstream_json = None
            if isinstance(upstream_json, dict) and isinstance(upstream_json.get("id"), str):
                record["provider_generation_id"] = upstream_json["id"]
            if drop:
                self.close_connection = True
                record["disposition"] = "dropped_after_upstream"
                return
            if proxy.delay_ms:
                time.sleep(proxy.delay_ms / 1000)
            response_headers = {
                key: value for key, value in response.headers.items()
                if key.lower() not in {
                    "content-encoding", "content-length", "transfer-encoding", "connection"
                }
            }
            self.send_response(response.status_code)
            for key, value in response_headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(response.content)))
            self.end_headers()
            self.wfile.write(response.content)
            record["disposition"] = "forwarded"
        except Exception as exc:  # pragma: no cover - exercised by live endpoint faults
            record.update({"disposition": "proxy_error", "error": type(exc).__name__})
            self.close_connection = True
        finally:
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            proxy.write_record(record)

    def log_message(self, *_args):
        return


class ProxyState:
    def __init__(self, args: argparse.Namespace):
        self.upstream = args.upstream
        self.delay_ms = args.delay_ms
        self.drop_remaining = args.drop_count
        self.max_body_bytes = args.max_body_bytes
        self.timeout_s = args.timeout_s
        self.log_path = args.log
        self._log = self.log_path.open("w", encoding="utf8")

    def write_record(self, value: dict) -> None:
        self._log.write(json.dumps(value, sort_keys=True) + "\n")
        self._log.flush()

    def close(self) -> None:
        self._log.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--upstream", default="https://openrouter.ai/api/v1/chat/completions")
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--drop-count", type=int, default=0)
    parser.add_argument("--max-body-bytes", type=int, default=2_000_000)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--log", type=Path, required=True)
    args = parser.parse_args()
    if args.port < 0 or args.delay_ms < 0 or args.drop_count < 0:
        parser.error("port, delay-ms, and drop-count must be nonnegative")
    if not os.environ.get("OPENROUTER_API_KEY"):
        parser.error("OPENROUTER_API_KEY must be set for the upstream")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    state = ProxyState(args)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), ProxyHandler)
    server.daemon_threads = True
    server.proxy_state = state
    server.timeout = 1
    print(json.dumps({"host": "127.0.0.1", "port": server.server_port}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        state.close()


if __name__ == "__main__":
    main()
