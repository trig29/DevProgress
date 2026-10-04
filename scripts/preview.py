#!/usr/bin/env python3
"""Serve only the generated site, optionally under a GitHub Pages project path."""
import argparse
import functools
import http.server
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=4173)
    parser.add_argument('--prefix', default='/DevProgress/')
    parser.add_argument('--directory', type=Path, default=ROOT/'site')
    args = parser.parse_args()
    prefix = '/'+args.prefix.strip('/')+'/' if args.prefix.strip('/') else '/'
    if not (args.directory/'index.html').exists():
        parser.error('Build the site before previewing')

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/', prefix.rstrip('/')) and prefix != '/':
                self.send_response(302)
                self.send_header('Location', prefix)
                self.end_headers()
                return
            if not path.startswith(prefix):
                self.send_error(404)
                return
            self.path = '/'+self.path[len(prefix):]
            super().do_GET()

        def end_headers(self):
            self.send_header('Cache-Control', 'no-store')
            super().end_headers()

        def list_directory(self, path):
            self.send_error(404)

    handler = functools.partial(Handler, directory=str(args.directory.resolve()))
    with http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler) as server:
        print(f'Preview: http://127.0.0.1:{args.port}{prefix}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
