# -*- coding: utf-8 -*-
"""MSL request building"""
from __future__ import unicode_literals

import json
import base64
import subprocess
import random

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
        self.tokens = []
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
        return json.dumps({
            'entityauthdata': {
                'scheme': 'NONE',
                'authdata': {'identity': esn}},
            'headerdata':
                base64.standard_b64encode(
                    self._headerdata(is_key_request=True, is_handshake=True,
                                     compression=None, esn=esn)),
            'signature': ''
        }, sort_keys=True)

    @common.time_execution(immediate=True)
    def _signed_header(self, esn):
        encryption_envelope = self.crypto.encrypt(self._headerdata(esn=esn),
                                                  esn)
        return {
            'headerdata': base64.standard_b64encode(encryption_envelope),
            'signature': self.crypto.sign(encryption_envelope),
            'mastertoken': self.crypto.mastertoken,
        }

    def _headerdata(self, esn, is_handshake=False, is_key_request=False,
                    compression='GZIP'):
        """
        Function that generates a MSL header dict
        :return: The base64 encoded JSON String of the header
        """
        self.current_message_id = self.rndm.randint(0, pow(2, 52))
        header_data = {
            'sender': esn,
            'handshake': is_handshake,
            'nonreplayable': False,
            'capabilities': {
                'languages': [g.LOCAL_DB.get_value('locale_id')],
                'compressionalgos': [compression] if compression else []
            },
            'recipient': 'Netflix',
            'renewable': True,
            'messageid': self.current_message_id,
            'timestamp': 1467733923
        }

        # If this is a keyrequest act different then other requests
        if is_key_request:
            header_data['keyrequestdata'] = self.crypto.key_request_data()
        else:
            _add_auth_info(header_data, self.tokens)

        return json.dumps(header_data)

    @common.time_execution(immediate=True)
    def _encrypted_chunk(self, data, esn):
        payload = {
            'messageid': self.current_message_id,
            'data': base64.standard_b64encode(json.dumps(data)),
            'sequencenumber': 1,
            'endofmsg': True
        }
        encryption_envelope = self.crypto.encrypt(json.dumps(payload), esn)
        return {
            'payload': base64.standard_b64encode(encryption_envelope),
            'signature': self.crypto.sign(encryption_envelope),
        }


def _add_auth_info(header_data, tokens):
    if 'usertoken' not in tokens:
        credentials = common.get_credentials()
        # Auth via email and password
        header_data['userauthdata'] = {
            'scheme': 'EMAIL_PASSWORD',
            'authdata': {
                'email': credentials['email'],
                'password': credentials['password']
            }
        }
