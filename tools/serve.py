"""Serve site/ locally with caching turned off, so the browser always picks up
fresh JS, CSS and data after an edit or rebuild.

    python tools/serve.py [port]
"""
import functools
import http.server
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    handler = functools.partial(NoCacheHandler, directory=str(SITE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"Serving {SITE} at http://127.0.0.1:{port}/ (no caching). Ctrl+C to stop.")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
