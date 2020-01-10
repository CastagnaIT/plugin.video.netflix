# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    MSL request building

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import json
import base64
import random
import subprocess

from resources.lib.globals import g
import resources.lib.common as common

# check if we are on Android
try:
    SDKVERSION = int(subprocess.check_output(
        ['/system/bin/getprop', 'ro.build.version.sdk']))
except (OSError, subprocess.CalledProcessError):
    SDKVERSION = 0

if SDKVERSION >= 18:
    from .android_crypto import AndroidMSLCrypto as MSLCrypto
else:
    from .default_crypto import DefaultMSLCrypto as MSLCrypto


class MSLRequestBuilder(object):
    """Provides mechanisms to create MSL requests"""
    def __init__(self, msl_data=None):
        self.current_message_id = None
        self.user_id_token = None
        self.rndm = random.SystemRandom()
        self.crypto = MSLCrypto(msl_data)

    @common.time_execution(immediate=True)
    def msl_request(self, data, esn):
        """Create an encrypted MSL request"""
        return (json.dumps(self._signed_header(esn)) +
                json.dumps(self._encrypted_chunk(data, esn)))

    @common.time_execution(immediate=True)
    def handshake_request(self, esn):
        """Create a key handshake request"""
        header = json.dumps({
            'entityauthdata': {
                'scheme': 'NONE',
                'authdata': {'identity': esn}},
            'headerdata':
                base64.standard_b64encode(
                    self._headerdata(is_handshake=True).encode('utf-8')).decode('utf-8'),
            'signature': ''
        }, sort_keys=True)
        payload = json.dumps(self._encrypted_chunk(envelope_payload=False))
        return header + payload

    @common.time_execution(immediate=True)
    def _signed_header(self, esn):
        encryption_envelope = self.crypto.encrypt(self._headerdata(esn=esn), esn)
        return {
            'headerdata': base64.standard_b64encode(
                encryption_envelope.encode('utf-8')).decode('utf-8'),
            'signature': self.crypto.sign(encryption_envelope),
            'mastertoken': self.crypto.mastertoken,
        }

    def _headerdata(self, esn=None, compression=None, is_handshake=False):
        """
        Function that generates a MSL header dict
        :return: The base64 encoded JSON String of the header
        """
        self.current_message_id = self.rndm.randint(0, pow(2, 52))
        header_data = {
            'messageid': self.current_message_id,
            'renewable': True,
            'capabilities': {
                'languages': [g.LOCAL_DB.get_value('locale_id')],
                'compressionalgos': [compression] if compression else []  # GZIP, LZW, Empty
            }
        }

        if is_handshake:
            header_data['keyrequestdata'] = self.crypto.key_request_data()
        else:
            header_data['sender'] = esn
            _add_auth_info(header_data, self.user_id_token)

        return json.dumps(header_data)

    @common.time_execution(immediate=True)
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


def _add_auth_info(header_data, user_id_token):
    """User authentication identifies the application user associated with a message"""
    if not user_id_token:
        credentials = common.get_credentials()
        # Authentication with the user credentials
        header_data['userauthdata'] = {
            'scheme': 'EMAIL_PASSWORD',
            'authdata': {
                'email': credentials['email'],
                'password': credentials['password']
            }
        }
    else:
        # Authentication with user ID token containing the user identity
        header_data['useridtoken'] = user_id_token
