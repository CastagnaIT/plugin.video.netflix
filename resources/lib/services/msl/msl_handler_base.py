# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2017 Trummerjo (original implementation module)
    Proxy service to convert manifest and provide license data

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import base64
import json
import re
import time
import zlib
from functools import wraps

import requests

import resources.lib.common as common
import resources.lib.kodi.ui as ui
from resources.lib.globals import g
from resources.lib.services.msl.exceptions import MSLError
from resources.lib.services.msl.request_builder import MSLRequestBuilder

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


CHROME_BASE_URL = 'https://www.netflix.com/nq/msl_v1/cadmium/'
ENDPOINTS = {
    'manifest': CHROME_BASE_URL + 'pbo_manifests/%5E1.0.0/router',  # "pbo_manifests/^1.0.0/router"
    'license': CHROME_BASE_URL + 'pbo_licenses/%5E1.0.0/router',
    'events': CHROME_BASE_URL + 'pbo_events/%5E1.0.0/router'
}


def display_error_info(func):
    """Decorator that catches errors raise by the decorated function,
    displays an error info dialog in the UI and reraises the error"""
    # pylint: disable=missing-docstring
    @wraps(func)
    def error_catching_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            ui.show_error_info(common.get_local_string(30028), unicode(exc),
                               unknown_error=not(unicode(exc)),
                               netflix_error=isinstance(exc, MSLError))
            raise
    return error_catching_wrapper


class MSLHandlerBase(object):
    """Handles session management and crypto for license, manifest and event requests"""
    last_license_url = ''
    last_drm_context = ''
    last_playback_context = ''
    session = requests.session()

    def __init__(self):
        self.request_builder = None

    def check_mastertoken_validity(self):
        """Return the mastertoken validity and executes a new key handshake when necessary"""
        if self.request_builder.crypto.mastertoken:
            time_now = time.time()
            renewable = self.request_builder.crypto.renewal_window < time_now
            expired = self.request_builder.crypto.expiration <= time_now
        else:
            renewable = False
            expired = True
        if expired:
            if not self.request_builder.crypto.mastertoken:
                common.debug('Stored MSL data not available, a new key handshake will be performed')
                self.request_builder = MSLRequestBuilder()
            else:
                common.debug('Stored MSL data is expired, a new key handshake will be performed')
            if self.perform_key_handshake():
                self.request_builder = MSLRequestBuilder(json.loads(
                    common.load_file('msl_data.json')))
            return self.check_mastertoken_validity()
        return {'renewable': renewable, 'expired': expired}


    @display_error_info
    @common.time_execution(immediate=True)
    def perform_key_handshake(self, data=None):
        """Perform a key handshake and initialize crypto keys"""
        # pylint: disable=unused-argument
        esn = data or g.get_esn()
        if not esn:
            common.info('Cannot perform key handshake, missing ESN')
            return False

        common.debug('Performing key handshake. ESN: {}', esn)

        response = _process_json_response(
            self._post(ENDPOINTS['manifest'],
                       self.request_builder.handshake_request(esn)))
        header_data = self.request_builder.decrypt_header_data(response['headerdata'], False)
        self.request_builder.crypto.parse_key_response(header_data, not common.is_edge_esn(esn))
        # Reset the user id token
        self.request_builder.user_id_token = None
        common.debug('Key handshake successful')
        return True

    @common.time_execution(immediate=True)
    def chunked_request(self, endpoint, request_data, esn, mt_validity=None):
        """Do a POST request and process the chunked response"""
        chunked_response = self._process_chunked_response(
            self._post(endpoint, self.request_builder.msl_request(request_data, esn)),
            mt_validity['renewable'] if mt_validity else None)
        return chunked_response['result']

    @common.time_execution(immediate=True)
    def _post(self, endpoint, request_data):
        """Execute a post request"""
        common.debug('Executing POST request to {}', endpoint)
        start = time.clock()
        response = self.session.post(endpoint, request_data)
        common.debug('Request took {}s', time.clock() - start)
        common.debug('Request returned response with status {}', response.status_code)
        response.raise_for_status()
        return response

    # pylint: disable=unused-argument
    @common.time_execution(immediate=True)
    def _process_chunked_response(self, response, mt_renewable):
        """Parse and decrypt an encrypted chunked response. Raise an error
        if the response is plaintext json"""
        try:
            # if the json() does not fail we have an error because
            # the expected response is a chunked json response
            return _raise_if_error(response.json())
        except ValueError:
            # json() failed so parse and decrypt the chunked response
            common.debug('Received encrypted chunked response')
            response = _parse_chunks(response.text)
            # TODO: sending for the renewal request is not yet implemented
            # if mt_renewable:
            #     # Check if mastertoken is renewed
            #     self.request_builder.crypto.compare_mastertoken(response['header']['mastertoken'])

            header_data = self.request_builder.decrypt_header_data(
                response['header'].get('headerdata'))

            if 'useridtoken' in header_data:
                # After the first call, it is possible get the 'user id token' that contains the
                # user identity to use instead of 'User Authentication Data' with user credentials
                self.request_builder.user_id_token = header_data['useridtoken']
            # if 'keyresponsedata' in header_data:
            #     common.debug('Found key handshake in response data')
            #     # Update current mastertoken
            #     self.request_builder.crypto.parse_key_response(header_data, True)
            decrypted_response = _decrypt_chunks(response['payloads'], self.request_builder.crypto)
            return _raise_if_error(decrypted_response)


def build_request_data(url, params=None, echo=''):
    """Create a standard request data"""
    if not params:
        raise Exception('Cannot build the message without parameters')
    timestamp = int(time.time() * 10000)
    request_data = {
        'version': 2,
        'url': url,
        'id': timestamp,
        'languages': [g.LOCAL_DB.get_value('locale_id')],
        'params': params,
        'echo': echo
    }
    return request_data


@common.time_execution(immediate=True)
def _process_json_response(response):
    """Execute a post request and expect a JSON response"""
    try:
        return _raise_if_error(response.json())
    except ValueError:
        raise MSLError('Expected JSON response, got {}'.format(response.text))


def _raise_if_error(decoded_response):
    raise_error = False
    # Catch a manifest/chunk error
    if any(key in decoded_response for key in ['error', 'errordata']):
        raise_error = True
    # Catch a license error
    if 'result' in decoded_response and isinstance(decoded_response.get('result'), list):
        if 'error' in decoded_response['result'][0]:
            raise_error = True
    if raise_error:
        common.error('Full MSL error information:')
        common.error(json.dumps(decoded_response))
        raise MSLError(_get_error_details(decoded_response))
    return decoded_response


def _get_error_details(decoded_response):
    # Catch a chunk error
    if 'errordata' in decoded_response:
        return json.loads(
            base64.standard_b64decode(
                decoded_response['errordata']))['errormsg']
    # Catch a manifest error
    if 'error' in decoded_response:
        if decoded_response['error'].get('errorDisplayMessage'):
            return decoded_response['error']['errorDisplayMessage']
    # Catch a license error
    if 'result' in decoded_response and isinstance(decoded_response.get('result'), list):
        if 'error' in decoded_response['result'][0]:
            if decoded_response['result'][0]['error'].get('errorDisplayMessage'):
                return decoded_response['result'][0]['error']['errorDisplayMessage']
    return 'Unhandled error check log.'


@common.time_execution(immediate=True)
def _parse_chunks(message):
    header = json.loads(message.split('}}')[0] + '}}')
    payloads = re.split(',\"signature\":\"[0-9A-Za-z=/+]+\"}',
                        message.split('}}')[1])
    payloads = [x + '}' for x in payloads][:-1]
    return {'header': header, 'payloads': payloads}


@common.time_execution(immediate=True)
def _decrypt_chunks(chunks, crypto):
    decrypted_payload = ''
    for chunk in chunks:
        payloadchunk = json.loads(chunk)
        payload = payloadchunk.get('payload')
        decoded_payload = base64.standard_b64decode(payload)
        encryption_envelope = json.loads(decoded_payload)
        # Decrypt the text
        plaintext = crypto.decrypt(
            base64.standard_b64decode(encryption_envelope['iv']),
            base64.standard_b64decode(encryption_envelope.get('ciphertext')))
        # unpad the plaintext
        plaintext = json.loads(plaintext)
        data = plaintext.get('data')

        # uncompress data if compressed
        if plaintext.get('compressionalgo') == 'GZIP':
            decoded_data = base64.standard_b64decode(data)
            data = zlib.decompress(decoded_data, 16 + zlib.MAX_WBITS).decode('utf-8')
        else:
            data = base64.standard_b64decode(data).decode('utf-8')

        decrypted_payload += data

    return json.loads(decrypted_payload)
