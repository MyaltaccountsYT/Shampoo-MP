import http.server
import socketserver
import os

PORT = 3000
WEBSITE_FILE = os.path.join(os.path.dirname(__file__), 'website.html')

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        with open(WEBSITE_FILE, 'rb') as f:
            self.wfile.write(f.read())

    def log_message(self, format, *args):
        print(f"[Web] {self.address_string()} - {format % args}")

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Shampoo MP website running at http://localhost:{PORT}")
    httpd.serve_forever()
