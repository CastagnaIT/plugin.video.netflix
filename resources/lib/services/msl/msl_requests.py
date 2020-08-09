# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2020 Stefano Gottardo
    MSL requests

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import base64
import json
import re
import zlib

import resources.lib.common as common
from resources.lib.common.exceptions import MSLError
from resources.lib.globals import G
from resources.lib.services.msl.msl_request_builder import MSLRequestBuilder
from resources.lib.services.msl.msl_utils import (display_error_info, generate_logblobs_params, EVENT_BIND, ENDPOINTS,
                                                  MSL_DATA_FILENAME)
from resources.lib.utils.esn import get_esn
from resources.lib.utils.logging import LOG, measure_exec_time_decorator, perf_clock

try:  # Python 2
    from urllib import urlencode
except ImportError:  # Python 3
    from urllib.parse import urlencode


class MSLRequests(MSLRequestBuilder):
    """Provides methods to make MSL requests"""

    def __init__(self, msl_data=None):
        super(MSLRequests, self).__init__()
        from requests import session
        self.session = session()
        self.session.headers.update({
            'User-Agent': common.get_user_agent(),
            'Content-Type': 'text/plain',
            'Accept': '*/*'
        })
        self._load_msl_data(msl_data)
        self.msl_switch_requested = False

    def _load_msl_data(self, msl_data):
        try:
            self.crypto.load_msl_data(msl_data)
            self.crypto.load_crypto_session(msl_data)
        except Exception:  # pylint: disable=broad-except
            import traceback
            LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))

    @display_error_info
    @measure_exec_time_decorator(is_immediate=True)
    def perform_key_handshake(self, data=None):  # pylint: disable=unused-argument
        """Perform a key handshake and initialize crypto keys"""
        esn = get_esn()
        if not esn:
            LOG.warn('Cannot perform key handshake, missing ESN')
            return False

        LOG.info('Performing key handshake with ESN: {}',
                 common.censure(esn) if G.ADDON.getSetting('esn') else esn)
        response = _process_json_response(self._post(ENDPOINTS['manifest'], self.handshake_request(esn)))
        header_data = self.decrypt_header_data(response['headerdata'], False)
        self.crypto.parse_key_response(header_data, esn, True)

        # Delete all the user id tokens (are correlated to the previous mastertoken)
        self.crypto.clear_user_id_tokens()
        LOG.debug('Key handshake successful')
        return True

    def _get_owner_user_id_token(self):
        """A way to get the user token id of owner profile"""
        # In order to get a user id token of another (non-owner) profile you must make a request with SWITCH_PROFILE
        # authentication scheme (a custom authentication for netflix), and this request can be directly included
        # in the MSL manifest request.
        # But in order to execute this switch profile, you need to have the user id token of the main (owner) profile.
        # The only way (found to now) to get it immediately, is send a logblob event request, and save the
        # user id token obtained in the response.
        LOG.debug('Requesting logblog')
        params = {'reqAttempt': 1,
                  'reqPriority': 0,
                  'reqName': EVENT_BIND}
        url = ENDPOINTS['logblobs'] + '?' + urlencode(params).replace('%2F', '/')
        response = self.chunked_request(url,
                                        self.build_request_data('/logblob', generate_logblobs_params()),
                                        get_esn(),
                                        force_auth_credential=True)
        LOG.debug('Response of logblob request: {}', response)

    def _mastertoken_checks(self):
        """Perform checks to the MasterToken and executes a new key handshake when necessary"""
        is_handshake_required = False
        if self.crypto.mastertoken:
            if self.crypto.is_current_mastertoken_expired():
                LOG.debug('Stored MSL MasterToken is expired, a new key handshake will be performed')
                is_handshake_required = True
            else:
                # Check if the current ESN is same of ESN bound to MasterToken
                if get_esn() != self.crypto.bound_esn:
                    LOG.debug('Stored MSL MasterToken is bound to a different ESN, '
                              'a new key handshake will be performed')
                    is_handshake_required = True
        else:
            LOG.debug('MSL MasterToken is not available, a new key handshake will be performed')
            is_handshake_required = True
        if is_handshake_required:
            if self.perform_key_handshake():
                msl_data = json.loads(common.load_file_def(MSL_DATA_FILENAME))
                self.crypto.load_msl_data(msl_data)
                self.crypto.load_crypto_session(msl_data)

    def _check_user_id_token(self, disable_msl_switch, force_auth_credential=False):
        """
        Performs user id token checks and return the auth data
        checks: uid token validity, get if needed the owner uid token, set when use the switch

        :param: disable_msl_switch: to be used in requests that cannot make the switch
        :param: force_auth_credential: force the use of authentication with credentials
        :return: auth data that will be used in MSLRequestBuilder _add_auth_info
        """
        # Warning: the user id token contains also contains the identity of the netflix profile
        # therefore it is necessary to use the right user id token for the request
        current_profile_guid = G.LOCAL_DB.get_active_profile_guid()
        owner_profile_guid = G.LOCAL_DB.get_guid_owner_profile()
        use_switch_profile = False
        user_id_token = None

        if not force_auth_credential:
            if current_profile_guid == owner_profile_guid:
                # The request will be executed from the owner profile
                # By default MSL is associated to the owner profile, then is not necessary get the owner token id
                # and it is not necessary use the MSL profile switch
                user_id_token = self.crypto.get_user_id_token(current_profile_guid)
                # The user_id_token can return None when the add-on is installed from scratch,
                # in this case will be used the authentication with the user credentials
            else:
                # The request will be executed from a non-owner profile
                # Get the non-owner profile token id, by checking that exists and it is valid
                user_id_token = self.crypto.get_user_id_token(current_profile_guid)
                if not user_id_token and not disable_msl_switch:
                    # The token does not exist/valid, you must set the MSL profile switch
                    use_switch_profile = True
                    # First check if the owner profile token exist and it is valid
                    user_id_token = self.crypto.get_user_id_token(owner_profile_guid)
                    if not user_id_token:
                        # The owner profile token id does not exist/valid, then get it
                        self._get_owner_user_id_token()
                        user_id_token = self.crypto.get_user_id_token(owner_profile_guid)
                    # Mark msl_switch_requested as True in order to make a bind event request
                    self.msl_switch_requested = True
        return {'use_switch_profile': use_switch_profile, 'user_id_token': user_id_token}

    @measure_exec_time_decorator(is_immediate=True)
    def chunked_request(self, endpoint, request_data, esn, disable_msl_switch=True, force_auth_credential=False):
        """Do a POST request and process the chunked response"""
        self._mastertoken_checks()
        auth_data = self._check_user_id_token(disable_msl_switch, force_auth_credential)
        LOG.debug('Chunked request will be executed with auth data: {}', auth_data)

        chunked_response = self._process_chunked_response(
            self._post(endpoint, self.msl_request(request_data, esn, auth_data)),
            save_uid_token_to_owner=auth_data['user_id_token'] is None)
        return chunked_response['result']

    def _post(self, endpoint, request_data):
        """Execute a post request"""
        LOG.debug('Executing POST request to {}', endpoint)
        start = perf_clock()
        response = self.session.post(endpoint, request_data)
        LOG.debug('Request took {}s', perf_clock() - start)
        LOG.debug('Request returned response with status {}', response.status_code)
        response.raise_for_status()
        return response

    # pylint: disable=unused-argument
    @measure_exec_time_decorator(is_immediate=True)
    def _process_chunked_response(self, response, save_uid_token_to_owner=False):
        """Parse and decrypt an encrypted chunked response. Raise an error
        if the response is plaintext json"""
        try:
            # if the json() does not fail we have an error because
            # the expected response is a chunked json response
            return _raise_if_error(response.json())
        except ValueError:
            # json() failed so parse and decrypt the chunked response
            LOG.debug('Received encrypted chunked response')
            response = _parse_chunks(response.text)
            # TODO: sending for the renewal request is not yet implemented
            # if self.crypto.get_current_mastertoken_validity()['is_renewable']:
            #     # Check if mastertoken is renewed
            #     self.request_builder.crypto.compare_mastertoken(response['header']['mastertoken'])

            header_data = self.decrypt_header_data(response['header'].get('headerdata'))

            if 'useridtoken' in header_data:
                # Save the user id token for the future msl requests
                profile_guid = G.LOCAL_DB.get_guid_owner_profile() if save_uid_token_to_owner else\
                    G.LOCAL_DB.get_active_profile_guid()
                self.crypto.save_user_id_token(profile_guid, header_data['useridtoken'])
            # if 'keyresponsedata' in header_data:
            #     LOG.debug('Found key handshake in response data')
            #     # Update current mastertoken
            #     self.request_builder.crypto.parse_key_response(header_data, True)
            decrypted_response = _decrypt_chunks(response['payloads'], self.crypto)
            return _raise_if_error(decrypted_response)


@measure_exec_time_decorator(is_immediate=True)
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
        LOG.error('Full MSL error information:')
        LOG.error(json.dumps(decoded_response))
        raise MSLError(_get_error_details(decoded_response))
    return decoded_response


def _get_error_details(decoded_response):
    # Catch a chunk error
    if 'errordata' in decoded_response:
        return G.py2_encode(json.loads(base64.standard_b64decode(decoded_response['errordata']))['errormsg'])
    # Catch a manifest error
    if 'error' in decoded_response:
        if decoded_response['error'].get('errorDisplayMessage'):
            return G.py2_encode(decoded_response['error']['errorDisplayMessage'])
    # Catch a license error
    if 'result' in decoded_response and isinstance(decoded_response.get('result'), list):
        if 'error' in decoded_response['result'][0]:
            if decoded_response['result'][0]['error'].get('errorDisplayMessage'):
                return G.py2_encode(decoded_response['result'][0]['error']['errorDisplayMessage'])
    return G.py2_encode('Unhandled error check log.')


@measure_exec_time_decorator(is_immediate=True)
def _parse_chunks(message):
    header = json.loads(message.split('}}')[0] + '}}')
    payloads = re.split(',\"signature\":\"[0-9A-Za-z=/+]+\"}', message.split('}}')[1])
    payloads = [x + '}' for x in payloads][:-1]
    return {'header': header, 'payloads': payloads}


@measure_exec_time_decorator(is_immediate=True)
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
