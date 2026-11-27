"""Observe the Harness Messages adapter's SSE text blocks before SDK aggregation."""
import json
import secrets
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic_core import from_json


@contextmanager
def model_stream(base, on_text):
    token = secrets.token_urlsafe(32)
    upstream = base.rstrip('/')
    if not upstream.endswith('/v1'):
        upstream += '/v1'

    failures = []

    class Relay(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path.split('?')[0] != '/' + token + '/v1/messages':
                self.send_error(404)
                return
            body = self.rfile.read(int(self.headers['Content-Length']))
            headers = {k:v for k,v in self.headers.items() if k.lower() in
                       ('authorization','x-api-key','anthropic-version','anthropic-beta','content-type','accept')}
            try:
                response = urlopen(Request(upstream+'/messages', data=body, headers=headers), timeout=120)
            except HTTPError as error:
                failures.append(f"公司模型接口返回 HTTP {error.code}，请稍后重试。")
                response = error
            except OSError:
                failures.append("未能连接公司模型，连接在收到回复前中断。请检查公司网络或 VPN 后重试。")
                self.send_error(400)
                return
            with response:
                self.send_response(response.status)
                self.send_header('Content-Type', response.headers.get('Content-Type','application/json'))
                self.end_headers()
                for line in response:
                    self.wfile.write(line)
                    self.wfile.flush()
                    if line.startswith(b'data:'):
                        try:
                            event = json.loads(line[5:])
                        except ValueError:
                            continue
                        delta = event.get('delta', {})
                        if event.get('type')=='content_block_delta' and delta.get('type')=='text_delta':
                            on_text(delta['text'])

    server = ThreadingHTTPServer(('127.0.0.1',0), Relay)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/{token}/v1'
    except Exception:
        if failures:
            raise ValueError(failures[-1]) from None
        raise
    finally:
        server.shutdown()
        server.server_close()


class ReplyStream:
    def __init__(self, emit, mid):
        self.emit = emit
        self.mid = mid
        self.raw = ''
        self.sent = ''

    def feed(self, text):
        self.raw += text
        start = self.raw.find('{')
        if start < 0:
            return
        try:
            obj = from_json(self.raw[start:].encode(), allow_partial='trailing-strings')
        except ValueError:
            return
        if isinstance(obj,dict) and isinstance(obj.get('reply'),str):
            self.append(obj['reply'])

    def append(self, reply):
        if reply.startswith(self.sent) and len(reply)>len(self.sent):
            if not self.sent:
                self.emit('TEXT_MESSAGE_START',messageId=self.mid,role='assistant')
            self.emit('TEXT_MESSAGE_CONTENT',messageId=self.mid,delta=reply[len(self.sent):])
            self.sent = reply
