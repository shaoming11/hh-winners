"""Standard-library HTTP server for the dashboard: the page, a Server-Sent Events feed of snapshots and an MJPEG
stream of the sim camera. It runs in daemon threads; the simulation stays on the main thread and talks to the
server only through ``Hub`` (latest snapshot JSON, latest JPEG, one Condition).

    GET  /                 index.html (web/)          GET /events        text/event-stream, one snapshot per message
    GET  /app.js, ...      other files in web/        GET /stream.mjpg   multipart/x-mixed-replace JPEG frames
    GET  /api/snapshot     latest snapshot JSON       POST /api/<cmd>    start | stop | reset  ->  {"ok", "message"}
"""
import http.server
import json
import math
import threading
from pathlib import Path

WEB = Path(__file__).parent / 'web'
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
         '.svg': 'image/svg+xml', '.png': 'image/png', '.mp4': 'video/mp4', '.json': 'application/json'}


def clean(o):
    """JSON-safe copy: numpy -> Python, NaN/inf -> None (the browser's JSON.parse rejects NaN)"""
    if isinstance(o, dict): return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [clean(v) for v in o]
    if hasattr(o, 'tolist'): return clean(o.tolist())
    if isinstance(o, float): return o if math.isfinite(o) else None
    if o is None or isinstance(o, (str, int, bool)): return o
    return str(o)


class Hub:
    def __init__(self):
        self.cond = threading.Condition(); self.snap = None; self.snap_ver = 0; self.jpeg = None; self.jpeg_ver = 0

    def publish(self, snap):
        s = snap if isinstance(snap, str) else json.dumps(clean(snap), allow_nan=False)
        with self.cond: self.snap = s; self.snap_ver += 1; self.cond.notify_all()

    def frame(self, jpeg):
        with self.cond: self.jpeg = jpeg; self.jpeg_ver += 1; self.cond.notify_all()

    def wait(self, attr, ver, timeout=10.0):
        """block until <attr>_ver moves past ver (or timeout) -> (ver, value)"""
        with self.cond:
            self.cond.wait_for(lambda: getattr(self, attr + '_ver') != ver, timeout)
            return getattr(self, attr + '_ver'), getattr(self, attr)


def make_handler(hub, control, web=WEB, extra_files=None):
    """control(cmd) -> (ok, message); extra_files: {url path: local Path} (replay video)"""
    files = {'/' + p.name: p for p in Path(web).iterdir() if p.is_file()}
    files['/'] = Path(web) / 'index.html'
    files.update(extra_files or {})

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def _send(self, code, body, ctype):
            self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body)

        def do_GET(self):
            path = self.path.split('?')[0]
            try:
                if path == '/events': return self._events()
                if path == '/stream.mjpg': return self._mjpeg()
                if path == '/api/snapshot': return self._send(200, (hub.snap or 'null').encode(), 'application/json')
                if path in files: return self._file(files[path])
                self._send(404, b'not found', 'text/plain')
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _file(self, p):
            self._send(200, p.read_bytes(), TYPES.get(p.suffix, 'application/octet-stream'))

        def do_POST(self):
            cmd = self.path.split('?')[0].rsplit('/', 1)[-1]
            if not self.path.startswith('/api/'): return self._send(404, b'not found', 'text/plain')
            ok, msg = control(cmd)
            self._send(200 if ok else 409, json.dumps(dict(ok=ok, message=msg)).encode(), 'application/json')

        def _events(self):
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Cache-Control', 'no-store')
            self.end_headers(); ver = -1
            while True:
                nv, snap = hub.wait('snap', ver, timeout=10.0)
                if nv != ver and snap is not None: self.wfile.write(b'data: ' + snap.encode() + b'\n\n')
                else: self.wfile.write(b': keepalive\n\n')
                self.wfile.flush(); ver = nv

        def _mjpeg(self):
            self.send_response(200); self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-store'); self.end_headers(); ver = -1
            while True:
                nv, jpg = hub.wait('jpeg', ver, timeout=10.0)
                if jpg is None or nv == ver: continue
                self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n' % len(jpg) + jpg + b'\r\n')
                self.wfile.flush(); ver = nv
    return Handler


def serve(hub, control, host='127.0.0.1', port=8765, **kw):
    """start the server in a daemon thread -> the server object (``.server_address`` has the bound port)"""
    srv = http.server.ThreadingHTTPServer((host, port), make_handler(hub, control, **kw)); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name='dashboard-http', daemon=True).start()
    return srv
