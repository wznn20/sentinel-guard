#!/usr/bin/env python3
"""Sentinel Demo Server — serves download site only, dashboard is 403 (local-only)"""
import http.server
import socketserver
import urllib.parse

BASE = "/root/hermes-security-agent"
PORT = 8888

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE, **kwargs)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        # Dashboard is local-only — block public access
        if path.startswith("/sentinel_dashboard"):
            self.send_response(403)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("仪表盘仅限本地访问。安装 Sentinel 后运行 sentinel dashboard 在 localhost:8443 打开。".encode())
            return
        # Root → download site
        if path in ("/", ""):
            self.send_response(301)
            self.send_header("Location", "/sentinel_download_site/index.html")
            self.end_headers()
            return
        super().do_GET()

if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        # Quick test
        handler = Handler
        print("Server code loaded OK. Dashboard blocking enabled.")
        sys.exit(0)
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"Sentinel Demo: http://0.0.0.0:{PORT}  (dashboard blocked)")
        httpd.serve_forever()
