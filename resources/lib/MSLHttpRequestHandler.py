import BaseHTTPServer
import base64
from urlparse import urlparse, parse_qs

from MSL import MSL
from lib import ADDON
email = ADDON.getSetting('email')
password = ADDON.getSetting('password')
msl = MSL(email, password)

class MSLHttpRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def do_HEAD(self):
        self.send_response(200)

    def do_POST(self):
        length = int(self.headers['content-length'])
        post = self.rfile.read(length)
        print post
        data = post.split('!')
        if len(data) is 2:
            challenge = data[0]
            sid = base64.standard_b64decode(data[1])
            b64license = msl.get_license(challenge, sid)
            if b64license is not '':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(base64.standard_b64decode(b64license))
                self.finish()
            else:
                self.send_response(400)
        else:
            self.send_response(400)

    def do_GET(self):
        url = urlparse(self.path)
        params = parse_qs(url.query)
        if 'id' not in params:
            self.send_response(400, 'No id')
        else:
            # Get the manifest with the given id
            data = msl.load_manifest(int(params['id'][0]))
            self.send_response(200)
            self.send_header('Content-type', 'application/xml')
            self.end_headers()
            self.wfile.write(data)
