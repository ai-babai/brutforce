"""Ephemeral organizer-contract bridge: multipart image in, one slug out."""
import argparse
import hashlib
import json
import time
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import Request, urlopen


class Handler(BaseHTTPRequestHandler):
    cascade_url = None
    audit_path = None

    def do_GET(self):
        if self.path != '/healthz':
            self.send_error(404)
            return
        self.respond(200, {'status':'ready','contract':'multipart-image-to-one-slug'})

    def do_POST(self):
        started = time.perf_counter()
        status = 500
        digest = None
        error = None
        try:
            if self.path != '/v1/eval/predict':
                status = 404
                self.send_error(404)
                return
            count = int(self.headers.get('Content-Length','0'))
            if not 0 < count <= 30_000_000:
                raise ValueError('Image body size')
            content_type = self.headers.get('Content-Type','')
            if not content_type.startswith('multipart/form-data'):
                raise ValueError('Expected multipart/form-data')
            raw = self.rfile.read(count)
            envelope = (b'Content-Type: '+content_type.encode()+b'\r\n'
                        b'MIME-Version: 1.0\r\n\r\n'+raw)
            multipart = BytesParser(policy=policy.default).parsebytes(envelope)
            image_part = next((part for part in multipart.iter_parts()
                if part.get_param('name',header='content-disposition') == 'image'), None)
            if image_part is None:
                raise ValueError('Missing multipart image field')
            image = image_part.get_payload(decode=True)
            if not image:
                raise ValueError('Empty image')
            digest = hashlib.sha256(image).hexdigest()
            request = Request(self.cascade_url,data=image,method='POST',
                headers={'Content-Type':'image/jpeg','X-Case-ID':'organizer-contract-'+digest[:12]})
            with urlopen(request,timeout=30) as response:
                if response.status != 200:
                    raise ValueError('Cascade HTTP status '+str(response.status))
                result = json.load(response)
            if result.get('query_sha256') != digest:
                raise ValueError('Cascade query SHA mismatch')
            ranked = result['roman20_ranked']
            if ranked and result['b_action'] == 'no_match':
                raise ValueError('B no-match/ranking conflict')
            status = 200
            self.respond(status, {'slug': ranked[0] if ranked else None})
        except Exception as exc:
            error = type(exc).__name__+': '+str(exc)[:180]
            status = 500
            self.respond(status, {'error':error})
        finally:
            record = {'sha256':digest,'http_status':status,
                'elapsed_ms':round((time.perf_counter()-started)*1000,3),'error':error}
            with self.audit_path.open('a') as out:
                out.write(json.dumps(record)+'\n')

    def respond(self, status, payload):
        content = json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(content)))
        self.end_headers()
        try:
            self.wfile.write(content)
        except BrokenPipeError:
            pass

    def log_message(self, fmt, *args):
        print('%s %s'%(self.address_string(), fmt%args), flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cascade-url',default='http://127.0.0.1:8092/v1/eval/predict?track=service')
    p.add_argument('--audit',type=Path,required=True)
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=8094)
    args=p.parse_args()
    Handler.cascade_url=args.cascade_url
    Handler.audit_path=args.audit
    print(json.dumps({'ready':True,'port':args.port,'cascade_url':args.cascade_url}),flush=True)
    HTTPServer((args.host,args.port),Handler).serve_forever()


if __name__=='__main__':
    main()
