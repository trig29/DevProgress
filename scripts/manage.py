#!/usr/bin/env python3
"""Local DevProgress manager. Python standard library only."""
import argparse
import errno
import hashlib
import hmac
import json
import mimetypes
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'scripts'))
from manager_store import Store, Conflict


def service_identity(root):
    return {'service':'devprogress-manager','project':hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()}


def existing_manager(root, port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=2) as response:
            return json.loads(response.read(4096))==service_identity(root)
    except (OSError,ValueError):
        return False


def make_handler(store, token, port):
    origin=f'http://127.0.0.1:{port}'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
        def send(self,status,data,mime='application/json; charset=utf-8'):
            raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode() if isinstance(data,(dict,list)) else data
            self.send_response(status)
            self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")
            self.end_headers();self.wfile.write(raw)
        def error(self,status,message):self.send(status,{'error':message})
        def auth(self, mutation=False):
            if self.headers.get('Host')!=f'127.0.0.1:{port}':self.error(403,'访问地址无效');return False
            if mutation and self.headers.get('Origin')!=origin:self.error(403,'写入仅允许来自本机管理页面');return False
            if not hmac.compare_digest(self.headers.get('X-Session-Token',''),token):self.error(403,'会话失效，请重新打开管理页');return False
            return True
        def file(self, root, relative):
            root=Path(root).resolve();p=(root/unquote(relative)).resolve()
            if not p.is_relative_to(root) or not p.is_file():self.error(404,'文件不存在');return
            self.send(200,p.read_bytes(),mimetypes.guess_type(p)[0] or 'application/octet-stream')
        def do_GET(self):
            if self.headers.get('Host')!=f'127.0.0.1:{port}':self.error(403,'访问地址无效');return
            path=urlsplit(self.path).path
            if path=='/api/health':
                self.send(200,service_identity(store.root))
            elif path=='/':
                html=(ROOT/'manager/index.html').read_text(encoding='utf-8').replace('__SESSION_TOKEN__',token)
                self.send(200,html.encode(),'text/html; charset=utf-8')
            elif path.startswith('/manager/'):
                self.file(ROOT/'manager',path[len('/manager/'):])
            elif path=='/api/state':
                if self.auth():self.send(200,store.state())
            elif path.startswith('/preview/'):
                self.file(store.root/'site',path[len('/preview/'):] or 'index.html')
            elif path.startswith('/draft-preview/'):
                if not store.preview_path:self.error(404,'请先校验并生成草稿预览');return
                self.file(store.preview_path/'site',path[len('/draft-preview/'):] or 'index.html')
            else:self.error(404,'接口不存在')
        def do_POST(self):
            if not self.auth(True):return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.error(415,'接口只接收 JSON');return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=4*1024*1024:raise ValueError('请求过大或为空')
                data=json.loads(self.rfile.read(size),parse_constant=lambda x: (_ for _ in ()).throw(ValueError('不允许非有限数值')))
                action=urlsplit(self.path).path
                routes={'/api/draft':store.save,'/api/discard':store.discard,'/api/validate':store.preview,'/api/apply':store.apply,'/api/restore':store.restore}
                if action not in routes:self.error(404,'接口不存在');return
                self.send(200,routes[action](data))
            except Conflict as exc:self.error(409,str(exc))
            except (ValueError,TypeError,KeyError,AttributeError) as exc:self.error(422,str(exc))
            except Exception:
                self.error(500,'操作失败；正式数据已回滚。请查看终端诊断。')
                import traceback;traceback.print_exc()
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=4174)
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--project',type=Path,default=ROOT,help='Only for isolated checks or another DevProgress checkout')
    args=parser.parse_args();store=Store(args.project)
    if not (store.root/'site/index.html').exists():
        from build_site import build
        build(store.root)
    try:server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(store,secrets.token_urlsafe(32),args.port))
    except OSError as exc:
        if exc.errno==errno.EADDRINUSE and existing_manager(store.root,args.port):
            url=f'http://127.0.0.1:{args.port}/'
            print(f'管理工具已在运行：{url}\n已复用现有服务，无需重复启动。',flush=True)
            if not args.no_open:webbrowser.open(url)
            return 2
        parser.exit(1,f'无法启动：端口 {args.port} 已被其他服务或旧版管理工具占用。\n可使用 python3 scripts/manage.py --port {args.port+1} 启动。\n原始错误：{exc}\n')
    url=f'http://127.0.0.1:{args.port}/'
    print(f'本地管理工具：{url}\n停止服务：在此终端按 Control+C。不会提交、推送或发布。',flush=True)
    if not args.no_open:threading.Timer(.4,lambda:webbrowser.open(url)).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':sys.exit(main())
