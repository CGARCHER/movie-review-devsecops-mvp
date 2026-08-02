"""API local para actualizar los informes del dashboard.

El navegador no ejecuta comandos del sistema. Este pequeño servicio recibe una
petición del dashboard y ejecuta únicamente el descargador configurado.
"""

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


UPDATE_LOCK = threading.Lock()
REQUEST_HEADER = "X-Dashboard-Request"


class ReportHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": "Ruta no encontrada."})

    def do_POST(self):
        if self.path != "/update":
            self.send_json(404, {"error": "Ruta no encontrada."})
            return

        # Esta cabecera evita que otra página pueda invocar el servicio
        # mediante una petición simple desde el navegador.
        if self.headers.get(REQUEST_HEADER) != "1":
            self.send_json(403, {"error": "Petición no autorizada."})
            return

        if not UPDATE_LOCK.acquire(blocking=False):
            self.send_json(409, {"error": "Ya hay una actualización en curso."})
            return

        try:
            result = subprocess.run(
                ["/usr/local/bin/security-report"],
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.send_json(504, {"error": "La descarga ha superado el tiempo máximo."})
            return
        finally:
            UPDATE_LOCK.release()

        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            self.send_json(
                502,
                {
                    "error": "No se ha podido actualizar el informe.",
                    "detail": output,
                },
            )
            return

        self.send_json(
            200,
            {
                "message": "Informe actualizado correctamente.",
                "detail": output,
            },
        )

    def log_message(self, message_format, *args):
        print(
            f"{self.client_address[0]} - {message_format % args}",
            flush=True,
        )


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), ReportHandler)
    print("API de informes disponible en el puerto 8080.", flush=True)
    server.serve_forever()
