# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Trummerjo (original implementation module)
    Handles & translates requests from Inputstream to Netflix

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
import base64

from resources.lib.globals import g

try:  # Python 3
    from urllib.parse import parse_qs, urlparse
except ImportError:  # Python 2
    from urlparse import urlparse, parse_qs

try:  # Python 3
    from http.server import BaseHTTPRequestHandler
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler

try:  # Python 3
    from socketserver import TCPServer
except ImportError:
    from SocketServer import TCPServer

import resources.lib.common as common

from .msl_handler import MSLHandler
from .exceptions import MSLError


class MSLHttpRequestHandler(BaseHTTPRequestHandler):
    """Handles & translates requests from Inputstream to Netflix"""
    # pylint: disable=invalid-name, broad-except
    def do_HEAD(self):
        """Answers head requests with a success code"""
        self.send_response(200)

    def do_POST(self):
        """Loads the licence for the requested resource"""
        try:
            url_parse = urlparse(self.path)
            common.debug('Handling HTTP POST IPC call to {}', url_parse.path)
            if '/license' not in url_parse:
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get('content-length', 0))
            data = self.rfile.read(length).decode('utf-8').split('!')
            b64license = self.server.msl_handler.get_license(
                challenge=data[0], sid=base64.standard_b64decode(data[1]).decode('utf-8'))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(base64.standard_b64decode(b64license))
        except Exception as exc:
            import traceback
            common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            self.send_response(500 if isinstance(exc, MSLError) else 400)
            self.end_headers()

    def do_GET(self):
        """Loads the XML manifest for the requested resource"""
        try:
            url_parse = urlparse(self.path)
            common.debug('Handling HTTP GET IPC call to {}', url_parse.path)
            if '/manifest' not in url_parse:
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(url_parse.query)
            data = self.server.msl_handler.load_manifest(int(params['id'][0]))
            self.send_response(200)
            self.send_header('Content-type', 'application/xml')
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            import traceback
            common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            self.send_response(500 if isinstance(exc, MSLError) else 400)
            self.end_headers()

    def log_message(self, *args):  # pylint: disable=arguments-differ
        """Disable the BaseHTTPServer Log"""


class MSLTCPServer(TCPServer):
    """Override TCPServer to allow usage of shared members"""
    def __init__(self, server_address):
        """Initialization of MSLTCPServer"""
        common.info('Constructing MSLTCPServer')
        self.msl_handler = MSLHandler()
        TCPServer.__init__(self, server_address, MSLHttpRequestHandler)
