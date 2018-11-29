# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Handles & translates requests from Inputstream to Netflix"""

import base64
import BaseHTTPServer
from urlparse import urlparse, parse_qs

from SocketServer import TCPServer
from resources.lib.MSLv2 import MSL


class MSLHttpRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """Handles & translates requests from Inputstream to Netflix"""

    # pylint: disable=invalid-name
    def do_HEAD(self):
        """Answers head requests with a success code"""
        self.send_response(200)

    # pylint: disable=invalid-name
    def do_POST(self):
        """Loads the licence for the requested resource"""
        length = int(self.headers.get('content-length'))
        post = self.rfile.read(length)
        data = post.split('!')
        if len(data) is 2:
            challenge = data[0]
            sid = base64.standard_b64decode(data[1])
            b64license = self.server.msl_handler.get_license(challenge, sid)
            if b64license is not '':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(base64.standard_b64decode(b64license))
                self.finish()
            else:
                self.server.nx_common.log(msg='Error getting License')
                self.send_response(400)
        else:
            self.server.nx_common.log(msg='Error in License Request')
            self.send_response(400)

    # pylint: disable=invalid-name
    def do_GET(self):
        """Loads the XML manifest for the requested resource"""
        url = urlparse(self.path)
        params = parse_qs(url.query)
        if 'id' not in params:
            self.send_response(400, 'No id')
        else:
            # Get the manifest with the given id
            dolby = (True if 'dolby' in params and
                     params['dolby'][0].lower() == 'true' else False)
            hevc = (True if 'hevc' in params and
                    params['hevc'][0].lower() == 'true' else False)
            hdr = (True if 'hdr' in params and
                    params['hdr'][0].lower() == 'true' else False)
            dolbyvision = (True if 'dolbyvision' in params and
                    params['dolbyvision'][0].lower() == 'true' else False)
            vp9 = (True if 'vp9' in params and
                    params['vp9'][0].lower() == 'true' else False)

            data = self.server.msl_handler.load_manifest(
                int(params['id'][0]),
                dolby, hevc, hdr, dolbyvision, vp9)

            self.send_response(200)
            self.send_header('Content-type', 'application/xml')
            self.end_headers()
            self.wfile.write(data)

    def log_message(self, *args):
        """Disable the BaseHTTPServer Log"""
        pass


##################################


class MSLTCPServer(TCPServer):
    """Override TCPServer to allow usage of shared members"""

    def __init__(self, server_address, nx_common):
        """Initialization of MSLTCPServer"""
        nx_common.log(msg='Constructing MSLTCPServer')
        self.nx_common = nx_common
        self.msl_handler = MSL(nx_common)
        TCPServer.__init__(self, server_address, MSLHttpRequestHandler)

    def reset_msl_data(self):
        """Initialization of MSLTCPServerResets MSL data (perform handshake)"""
        self.msl_handler.perform_key_handshake()
