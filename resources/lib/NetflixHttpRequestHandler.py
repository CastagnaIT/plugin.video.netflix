# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: NetflixHttpRequestHandler
# Created on: 07.03.2017

import BaseHTTPServer
import json
from types import FunctionType
from urlparse import urlparse, parse_qs
from resources.lib.KodiHelper import KodiHelper
from resources.lib.NetflixSession import NetflixSession
from resources.lib.NetflixHttpSubRessourceHandler import NetflixHttpSubRessourceHandler

kodi_helper = KodiHelper()

netflix_session = NetflixSession(
    cookie_path=kodi_helper.cookie_path,
    data_path=kodi_helper.data_path,
    verify_ssl=kodi_helper.get_ssl_verification_setting(),
    log_fn=kodi_helper.log
)

# get list of methods & instance form the sub ressource handler
methods = [x for x, y in NetflixHttpSubRessourceHandler.__dict__.items() if type(y) == FunctionType]
sub_res_handler = NetflixHttpSubRessourceHandler(kodi_helper=kodi_helper, netflix_session=netflix_session)

class NetflixHttpRequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    """ Represents the callable internal server that dispatches requests to Netflix"""

    def do_GET(self):
        """GET request handler (we only need this, as we only do GET requests internally)"""
        url = urlparse(self.path)
        params = parse_qs(url.query)
        method = params.get('method', [None])[0]

        # not method given
        if method == None:
            self.send_error(500, 'No method declared')
            return

        # no existing method given
        if method not in methods:
            self.send_error(404, 'Method "' + str(method) + '" not found. Available methods: ' + str(methods))
            return

        # call method & get the result
        result = getattr(sub_res_handler, method)(params)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'method': method, 'result': result}));
        return

    def log_message(self, format, *args):
        """Disable the BaseHTTPServer Log"""
        return
