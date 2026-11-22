"""web.py: lida com porta ocupada (ex.: janela antiga do Studio ainda aberta)."""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import web


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def serve(payload, status=200):
    """Servidor HTTP mínimo que responde `payload` em qualquer GET; devolve (porta, parar)."""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1], srv.shutdown


def test_port_free_e_find_free_port():
    port = free_port()
    assert web.port_free(port)
    with socket.socket() as s:
        s.bind(('127.0.0.1', port))
        assert not web.port_free(port)
        assert web.find_free_port(port) != port  # pula a porta ocupada
    assert web.find_free_port(port) == port


def test_faceless_info_reconhece_instancia_nova_e_antiga():
    port, stop = serve({'version': '9.9.9', 'providers': ['gemini'], 'layouts': []})
    try:
        assert web.faceless_info(port)['version'] == '9.9.9'
    finally:
        stop()
    port, stop = serve({'providers': ['gemini'], 'layouts': []})  # versões antigas não informavam a versão
    try:
        info = web.faceless_info(port)
        assert info is not None and 'version' not in info
    finally:
        stop()


def test_faceless_info_ignora_outros_programas_e_portas_vazias():
    port, stop = serve({'ola': 'mundo'})
    try:
        assert web.faceless_info(port) is None  # responde JSON, mas não é o Studio
    finally:
        stop()
    assert web.faceless_info(free_port()) is None  # ninguém escutando
