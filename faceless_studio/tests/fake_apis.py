"""Servidor local que imita as APIs de imagem (OpenAI, Gemini, Pollinations, ComfyUI) para testes."""
import base64
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from PIL import Image, ImageDraw


def fake_png(w=1536, h=1024, seed=0):
    im = Image.new('RGB', (w, h), (20 + seed % 60, 60, 90))
    d = ImageDraw.Draw(im)
    for k in range(12):
        x = (k * 137 + seed * 31) % w
        d.ellipse((x, h * 0.2 + k * 20, x + w * 0.25, h * 0.2 + k * 20 + w * 0.25),
                  outline=(120, 230, 210), width=6)
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()


class State:
    requests = []
    gemini_reject_first = True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(n) or b'{}')

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._json()
        State.requests.append(('POST', path, dict(self.headers), body))
        if path == '/v1/images/generations':
            if self.headers.get('Authorization') != 'Bearer test-openai':
                return self._send(401, {'error': {'message': 'bad key'}})
            return self._send(200, {'data': [{'b64_json': base64.b64encode(fake_png()).decode()}]})
        if path.endswith(':generateContent'):
            if self.headers.get('x-goog-api-key') != 'test-gemini':
                return self._send(403, {'error': 'bad key'})
            if State.gemini_reject_first and 'imageConfig' in body.get('generationConfig', {}):
                return self._send(400, {'error': {'message': 'Unknown name "imageConfig"'}})
            return self._send(200, {'candidates': [{'content': {'parts': [
                {'text': 'aqui está'},
                {'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(fake_png(1344, 768)).decode()}}]}}]})
        if path == '/prompt':
            State.last_comfy = body['prompt']
            return self._send(200, {'prompt_id': 'abc123', 'number': 1})
        self._send(404, {'error': 'not found'})

    def do_GET(self):
        u = urlparse(self.path)
        State.requests.append(('GET', u.path, dict(self.headers), parse_qs(u.query)))
        if u.path.startswith('/prompt/') or u.path.startswith('/image/'):
            q = parse_qs(u.query)
            return self._send(200, fake_png(int(q['width'][0]), int(q['height'][0]), int(q['seed'][0]) % 1000),
                              'image/jpeg')
        if u.path == '/history/abc123':
            return self._send(200, {'abc123': {'status': {'status_str': 'success', 'completed': True},
                                               'outputs': {'9': {'images': [{'filename': 'faceless_0001.png',
                                                                             'subfolder': '', 'type': 'output'}]}}}})
        if u.path == '/view':
            return self._send(200, fake_png(1344, 768), 'image/png')
        self._send(404, {'error': 'not found'})


def start():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'
