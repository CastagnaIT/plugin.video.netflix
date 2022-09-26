# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    MSL request building

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
import base64
import random
import time
from typing import TYPE_CHECKING

from resources.lib.common.exceptions import MSLError
from resources.lib.globals import G
import resources.lib.common as common
from resources.lib.services.nfsession.msl.msl_utils import (MSL_AUTH_USER_ID_TOKEN, MSL_AUTH_EMAIL_PASSWORD,
                                                            MSL_AUTH_NETFLIXID)
from resources.lib.utils.logging import measure_exec_time_decorator

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations


class MSLRequestBuilder:
    """Provides mechanisms to create MSL requests"""

    def __init__(self, nfsession):
        self.nfsession: 'NFSessionOperations' = nfsession
        self.current_message_id = None
        self.rndm = random.SystemRandom()
        # Set the Crypto handler
        if common.get_system_platform() == 'android':
            from .android_crypto import AndroidMSLCrypto as MSLCrypto
        else:
            from .default_crypto import DefaultMSLCrypto as MSLCrypto
        self.crypto = MSLCrypto()

    @staticmethod
    def build_request_data(url, params=None, echo=''):
        """Create a standard request data"""
        timestamp = int(time.time() * 10000)
        request_data = {
            'version': 2,
            'url': url,
            'id': timestamp,
            'languages': [G.LOCAL_DB.get_profile_config('language')],
            'params': params,
            'echo': echo
        }
        return request_data

    @measure_exec_time_decorator(is_immediate=True)
    def msl_request(self, data, esn, auth_data):
        """Create an encrypted MSL request"""
        return (json.dumps(self._signed_header(esn, auth_data)) +
                json.dumps(self._encrypted_chunk(data, esn)))

    @measure_exec_time_decorator(is_immediate=True)
    def handshake_request(self, esn):
        """Create a key handshake request"""
        header = json.dumps({
            'entityauthdata': {
                'scheme': 'NONE',
                'authdata': {'identity': esn}},
            'headerdata':
                base64.standard_b64encode(
                    self._headerdata(auth_data={}, is_handshake=True).encode('utf-8')).decode('utf-8'),
            'signature': ''
        }, sort_keys=True)
        payload = json.dumps(self._encrypted_chunk(envelope_payload=False))
        return header + payload

    def _signed_header(self, esn, auth_data):
        encryption_envelope = self.crypto.encrypt(self._headerdata(auth_data=auth_data, esn=esn), esn)
        return {
            'headerdata': base64.standard_b64encode(
                encryption_envelope.encode('utf-8')).decode('utf-8'),
            'signature': self.crypto.sign(encryption_envelope),
            'mastertoken': self.crypto.mastertoken,
        }

    def _headerdata(self, auth_data, esn=None, compression=None, is_handshake=False):
        """
        Function that generates a MSL header dict
        :return: The base64 encoded JSON String of the header
        """
        self.current_message_id = self.rndm.randint(0, pow(2, 52))
        header_data = {
            'messageid': self.current_message_id,
            'renewable': True,
            'capabilities': {
                'languages': [G.LOCAL_DB.get_value('locale_id')],
                'compressionalgos': [compression] if compression else []  # GZIP, LZW, Empty
            }
        }

        if is_handshake:
            header_data['keyrequestdata'] = self.crypto.key_request_data()
        else:
            header_data['sender'] = esn
            self._add_auth_info(header_data, auth_data)

        return json.dumps(header_data)

    def _encrypted_chunk(self, data='', esn=None, envelope_payload=True):
        if data:
            data = base64.standard_b64encode(json.dumps(data).encode('utf-8')).decode('utf-8')
        payload = json.dumps({
            'messageid': self.current_message_id,
            'data': data,
            'sequencenumber': 1,
            'endofmsg': True
        })
        if envelope_payload:
            payload = self.crypto.encrypt(payload, esn)
        return {
            'payload': base64.standard_b64encode(payload.encode('utf-8')).decode('utf-8'),
            'signature': self.crypto.sign(payload) if envelope_payload else '',
        }

    def decrypt_header_data(self, data, enveloped=True):
        """Decrypt a message header"""
        header_data = json.loads(base64.standard_b64decode(data))
        if enveloped:
            init_vector = base64.standard_b64decode(header_data['iv'])
            cipher_text = base64.standard_b64decode(header_data['ciphertext'])
            return json.loads(self.crypto.decrypt(init_vector, cipher_text))
        return header_data

    def _add_auth_info(self, header_data, auth_data):
        """User authentication identifies the application user associated with a message"""
        if auth_data['auth_scheme'] == MSL_AUTH_USER_ID_TOKEN:
            # Authentication scheme with: User ID token
            # Make requests by using by default main netflix profile, since the user id token contains also the identity
            # of the netflix profile, to send data to the right profile (e.g. for continue watching) must be used
            # SWITCH_PROFILE scheme to switching MSL profile.
            # 25/09/2022: SWITCH_PROFILE auth scheme has been disabled on netflix website backend and not works anymore.
            if auth_data['use_switch_profile']:
                # The SWITCH_PROFILE is a custom Netflix MSL user authentication scheme, that is needed for switching
                # profile on MSL side, works only combined with user id token and can not be used with all endpoints
                # after use it you will get the user id token of the requested profile in the response.
                header_data['userauthdata'] = {
                    'scheme': 'SWITCH_PROFILE',
                    'authdata': {
                        'useridtoken': auth_data['user_id_token'],
                        'profileguid': G.LOCAL_DB.get_active_profile_guid()
                    }
                }
            else:
                header_data['useridtoken'] = auth_data['user_id_token']
        elif auth_data['auth_scheme'] == MSL_AUTH_EMAIL_PASSWORD:
            # Authentication scheme with: Email password
            # Make requests by using main netflix profile only (you cannot update continue watching to other profiles)
            credentials = common.get_credentials()
            header_data['userauthdata'] = {
                'scheme': 'EMAIL_PASSWORD',
                'authdata': {
                    'email': credentials['email'],
                    'password': credentials['password']
                }
            }
        elif auth_data['auth_scheme'] == MSL_AUTH_NETFLIXID:
            # Authentication scheme with: Netflix ID cookies
            # Make requests by using the same netflix profile used/set on nfsession (website)
            header_data['userauthdata'] = {
                'scheme': 'NETFLIXID',
                'authdata': {
                    'netflixid': self.nfsession.session.cookies['NetflixId'],
                    'securenetflixid': self.nfsession.session.cookies['SecureNetflixId']
                }
            }
        else:
            raise MSLError(f'Authentication scheme "{auth_data["auth_scheme"]}" is not supported.')
