"""Servidor local del reproductor con soporte de rangos HTTP."""
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_VIDEO_SERVE = {"server": None, "port": None, "path": None, "error": ""}


class _VideoFileHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silenciar el log del servidor
        pass

    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Access-Control-Expose-Headers",
                         "Content-Range, Accept-Ranges, Content-Length")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.end_headers()

    def do_HEAD(self):
        self._serve(head_only=True)

    def do_GET(self):
        self._serve(head_only=False)

    def _serve(self, head_only):
        path = _VIDEO_SERVE.get("path")
        if not path or not os.path.isfile(path):
            self.send_response(404)
            self._send_cors()
            self.end_headers()
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            self.send_response(404)
            self._send_cors()
            self.end_headers()
            return
        start, end = 0, size - 1
        rango = self.headers.get("Range")
        if rango:
            m = re.match(r"bytes=(\d*)-(\d*)", rango.strip())
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self._send_cors()
                    self.end_headers()
                    return
        length = end - start + 1
        ctype = mimetypes.guess_type(path)[0] or "video/mp4"
        self.send_response(206 if rango else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if rango:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self._send_cors()
        self.end_headers()
        if head_only:
            return
        try:
            with open(path, "rb") as f:
                f.seek(start)
                restante = length
                while restante > 0:
                    trozo = f.read(min(1024 * 1024, restante))
                    if not trozo:
                        break
                    self.wfile.write(trozo)
                    restante -= len(trozo)
        except (BrokenPipeError, ConnectionResetError):
            pass


def servir_video(ruta):
    """Sirve el vídeo local por HTTP y devuelve su URL, o "" si no se puede.
    El servidor se crea una sola vez (mismo puerto); si cambia la ruta, solo
    cambia el archivo servido y la URL sigue siendo la misma."""
    ruta = str(ruta)
    if not os.path.isfile(ruta):
        return ""
    from playback_media import media_version
    version = media_version(ruta)
    srv = _VIDEO_SERVE.get("server")
    if srv is not None and _VIDEO_SERVE.get("path") == ruta:
        return f"http://127.0.0.1:{_VIDEO_SERVE['port']}/video.mp4?v={version}"
    _VIDEO_SERVE["path"] = ruta
    if srv is None:
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", 0), _VideoFileHandler)
            srv.daemon_threads = True
            _VIDEO_SERVE["server"] = srv
            _VIDEO_SERVE["port"] = srv.server_address[1]
            _VIDEO_SERVE["error"] = ""
            threading.Thread(target=srv.serve_forever, daemon=True).start()
        except OSError as err:
            _VIDEO_SERVE["server"] = None
            _VIDEO_SERVE["error"] = str(err)
            return ""
    return f"http://127.0.0.1:{_VIDEO_SERVE['port']}/video.mp4?v={version}"


