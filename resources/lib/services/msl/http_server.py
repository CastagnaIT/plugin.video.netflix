# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Trummerjo (original implementation module)
    Handles & translates requests from Inputstream to Netflix

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import base64
import json
from http.server import BaseHTTPRequestHandler
from socketserver import TCPServer
from urllib.parse import parse_qs, urlparse

from resources.lib import common
from resources.lib.common.exceptions import MSLError
from resources.lib.utils.logging import LOG
from .msl_handler import MSLHandler


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
            LOG.debug('Handling HTTP POST IPC call to {}', url_parse.path)
            if '/license' in url_parse:
                length = int(self.headers.get('content-length', 0))
                data = self.rfile.read(length).decode('utf-8').split('!')
                b64license = self.server.msl_handler.get_license(
                    challenge=data[0], sid=base64.standard_b64decode(data[1]).decode('utf-8'))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(base64.standard_b64decode(b64license))
            else:
                func_name = self.path[1:]
                length = int(self.headers.get('content-length', 0))
                data = json.loads(self.rfile.read(length)) or None
                try:
                    result = self.server.msl_handler.http_ipc_slots[func_name](data)
                    if isinstance(result, dict) and common.IPC_EXCEPTION_PLACEHOLDER in result:
                        self.send_response(500, json.dumps(result))
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode('utf-8'))
                except KeyError:
                    self.send_response(500, json.dumps(
                        common.ipc_convert_exc_to_json(class_name='SlotNotImplemented',
                                                       message='The specified slot {} does not exist'.format(func_name))
                    ))
                    self.end_headers()
        except Exception as exc:
            import traceback
            LOG.error(traceback.format_exc())
            self.send_response(500 if isinstance(exc, MSLError) else 400)
            self.end_headers()

    def do_GET(self):
        """Loads the XML manifest for the requested resource"""
        try:
            url_parse = urlparse(self.path)
            LOG.debug('Handling HTTP GET IPC call to {}', url_parse.path)
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
            LOG.error(traceback.format_exc())
            self.send_response(500 if isinstance(exc, MSLError) else 400)
            self.end_headers()

    def log_message(self, *args):  # pylint: disable=arguments-differ
        """Disable the BaseHTTPServer Log"""


class MSLTCPServer(TCPServer):
    """Override TCPServer to allow usage of shared members"""
    def __init__(self, server_address):
        """Initialization of MSLTCPServer"""
        LOG.info('Constructing MSLTCPServer')
        self.msl_handler = MSLHandler()
        super().__init__(server_address, MSLHttpRequestHandler)
