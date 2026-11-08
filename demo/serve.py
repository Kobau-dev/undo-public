"""Serve the demo apps: python -m undo demo  (or python demo/serve.py [port])."""
from __future__ import annotations

import functools
import http.server
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).parent


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # pages change between runs; never show a stale one
        super().end_headers()


def serve(port: int = 8765) -> None:
    handler = functools.partial(NoCacheHandler, directory=str(DEMO_DIR))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Undo demo apps: http://localhost:{port}/  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
