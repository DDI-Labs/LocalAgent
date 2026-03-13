"""Mock booking verification server.

Serves a simple HTML page that displays a parking pass / booking record
when queried by license plate. The CUA agent navigates here, reads the
screen, and decides GRANTED or DENIED based on what it sees.

Runs on localhost:5555 by default.
"""

import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from testserver.data import lookup

log = logging.getLogger(__name__)

TEST_SERVER_PORT = 5555


def _render_landing() -> str:
    """Home page with a search form."""
    return """\
<!DOCTYPE html>
<html>
<head><title>Parking Verification System</title>
<style>
  body { font-family: Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 40px; }
  .container { max-width: 600px; margin: 0 auto; background: #fff; border-radius: 12px;
               padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
  h1 { color: #1a1a2e; font-size: 28px; margin-bottom: 8px; }
  .subtitle { color: #666; font-size: 16px; margin-bottom: 32px; }
  label { font-weight: bold; font-size: 18px; display: block; margin-bottom: 8px; }
  input[type=text] { width: 100%; padding: 14px; font-size: 20px; border: 2px solid #ddd;
                     border-radius: 8px; box-sizing: border-box; }
  input[type=text]:focus { border-color: #4a90d9; outline: none; }
  button { margin-top: 16px; padding: 14px 32px; font-size: 18px; font-weight: bold;
           background: #4a90d9; color: #fff; border: none; border-radius: 8px; cursor: pointer; }
  button:hover { background: #357abd; }
</style>
</head>
<body>
<div class="container">
  <h1>Parking Verification System</h1>
  <p class="subtitle">Enter a license plate number to look up the booking.</p>
  <form method="GET" action="/verify">
    <label for="plate">License Plate</label>
    <input type="text" id="plate" name="plate" placeholder="e.g. ABC-1234" autofocus>
    <br>
    <button type="submit">Search</button>
  </form>
</div>
</body>
</html>"""


def _render_result(plate: str) -> str:
    """Result page — shows booking pass or 'not found'."""
    booking = lookup(plate)

    if booking is None:
        body = f"""\
  <div class="result not-found">
    <h2>No Booking Found</h2>
    <p class="plate">{plate}</p>
    <p class="message">No active parking pass exists for this license plate.</p>
    <p class="message">The vehicle is not registered in the system.</p>
  </div>"""
    else:
        status_class = booking["status"]
        status_label = booking["status"].upper()
        body = f"""\
  <div class="result found">
    <h2>Parking Pass</h2>
    <table>
      <tr><td class="label">License Plate</td><td class="value">{booking['plate']}</td></tr>
      <tr><td class="label">Driver</td><td class="value">{booking['driver']}</td></tr>
      <tr><td class="label">Building</td><td class="value">{booking['building']}</td></tr>
      <tr><td class="label">Bay</td><td class="value">{booking['bay']}</td></tr>
      <tr><td class="label">Reason</td><td class="value">{booking['reason']}</td></tr>
      <tr><td class="label">Pass Status</td><td class="value status-{status_class}">{status_label}</td></tr>
    </table>
  </div>"""

    return f"""\
<!DOCTYPE html>
<html>
<head><title>Verification Result — {plate}</title>
<style>
  body {{ font-family: Arial, sans-serif; background: #f0f2f5; margin: 0; padding: 40px; }}
  .container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 12px;
               padding: 40px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h2 {{ font-size: 26px; margin-bottom: 20px; }}
  .plate {{ font-size: 32px; font-weight: bold; color: #c0392b; letter-spacing: 2px; }}
  .message {{ font-size: 20px; color: #555; margin-top: 12px; }}
  .not-found {{ text-align: center; }}
  .not-found h2 {{ color: #c0392b; }}
  .found h2 {{ color: #27674a; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td {{ padding: 12px 16px; font-size: 18px; border-bottom: 1px solid #eee; }}
  .label {{ font-weight: bold; color: #555; width: 40%; }}
  .value {{ color: #1a1a2e; }}
  .status-active {{ color: #27ae60; font-weight: bold; font-size: 20px; }}
  .status-expired {{ color: #e67e22; font-weight: bold; font-size: 20px; }}
  .status-suspended {{ color: #c0392b; font-weight: bold; font-size: 20px; }}
  .back {{ display: inline-block; margin-top: 24px; color: #4a90d9; text-decoration: none; font-size: 16px; }}
</style>
</head>
<body>
<div class="container">
{body}
  <a class="back" href="/">← Search another plate</a>
</div>
</body>
</html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/verify":
            params = parse_qs(parsed.query)
            plate = params.get("plate", [""])[0]
            if plate:
                html = _render_result(plate)
            else:
                html = _render_landing()
        else:
            html = _render_landing()

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, fmt, *args):
        # Suppress default stderr logging
        pass


def start_test_server(port: int = TEST_SERVER_PORT) -> None:
    """Start the mock server in a daemon thread. Returns immediately."""
    def _serve():
        server = HTTPServer(("127.0.0.1", port), _Handler)
        log.info("Test verification server running on http://127.0.0.1:%d", port)
        server.serve_forever()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
