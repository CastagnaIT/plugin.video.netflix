# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H
"""Handles & translates requests from Inputstream to Netflix"""
from __future__ import absolute_import, division, unicode_literals
import base64

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
            length = int(self.headers.get('content-length', 0))
            data = self.rfile.read(length).decode('utf-8').split('!')
            b64license = self.server.msl_handler.get_license(
                challenge=data[0], sid=base64.standard_b64decode(data[1]).decode('utf-8'))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(base64.standard_b64decode(b64license))
            self.finish()
        except Exception as exc:
            import traceback
            common.error(traceback.format_exc())
            self.send_response(500 if isinstance(exc, MSLError) else 400)

    def do_GET(self):
        """Loads the XML manifest for the requested resource"""
        try:
            params = parse_qs(urlparse(self.path).query)
            data = self.server.msl_handler.load_manifest(int(params['id'][0]))
            self.send_response(200)
            self.send_header('Content-type', 'application/xml')
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            import traceback
            common.error(traceback.format_exc())
            self.send_response(500 if isinstance(exc, MSLError) else 400)

    def log_message(self, *args):  # pylint: disable=arguments-differ
        """Disable the BaseHTTPServer Log"""


class MSLTCPServer(TCPServer):
    """Override TCPServer to allow usage of shared members"""
    def __init__(self, server_address):
        """Initialization of MSLTCPServer"""
        common.info('Constructing MSLTCPServer')
        self.msl_handler = MSLHandler()
        TCPServer.__init__(self, server_address, MSLHttpRequestHandler)
