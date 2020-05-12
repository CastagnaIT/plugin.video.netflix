# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Crypto handler for Android platforms

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import base64
import json

import xbmcdrm

import resources.lib.common as common
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import g
from .base_crypto import MSLBaseCrypto
from .exceptions import MSLError


class AndroidMSLCrypto(MSLBaseCrypto):
    """Crypto handler for Android platforms"""
    def __init__(self):
        super(AndroidMSLCrypto, self).__init__()
        self.crypto_session = None
        self.keyset_id = None
        self.key_id = None
        self.hmac_key_id = None
        try:
            self.crypto_session = xbmcdrm.CryptoSession(
                'edef8ba9-79d6-4ace-a3c8-27dcd51d21ed', 'AES/CBC/NoPadding', 'HmacSHA256')
            common.debug('Widevine CryptoSession successful constructed')
        except Exception:  # pylint: disable=broad-except
            import traceback
            common.error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            raise MSLError('Failed to construct Widevine CryptoSession')

        drm_info = {
            'version': self.crypto_session.GetPropertyString('version'),
            'system_id': self.crypto_session.GetPropertyString('systemId'),
            #  'device_unique_id': self.crypto_session.GetPropertyByteArray('deviceUniqueId')
            'hdcp_level': self.crypto_session.GetPropertyString('hdcpLevel'),
            'hdcp_level_max': self.crypto_session.GetPropertyString('maxHdcpLevel'),
            'security_level': self.crypto_session.GetPropertyString('securityLevel')
        }

        if not drm_info['version']:
            # Possible cases where no data is obtained:
            # - Device with custom ROM or without Widevine support
            # - Using Kodi debug build with a InputStream Adaptive release build (yes users do it)
            raise MSLError('It was not possible to get the data from Widevine CryptoSession.\r\n'
                           'Your system is not Widevine certified or you have a wrong Kodi version installed.')

        g.LOCAL_DB.set_value('drm_system_id', drm_info['system_id'], TABLE_SESSION)
        g.LOCAL_DB.set_value('drm_security_level', drm_info['security_level'], TABLE_SESSION)
        g.LOCAL_DB.set_value('drm_hdcp_level', drm_info['hdcp_level'], TABLE_SESSION)

        common.debug('Widevine version: {}', drm_info['version'])
        if drm_info['system_id']:
            common.debug('Widevine CryptoSession system id: {}', drm_info['system_id'])
        else:
            common.warn('Widevine CryptoSession system id not obtained!')
        common.debug('Widevine CryptoSession security level: {}', drm_info['security_level'])
        common.debug('Widevine CryptoSession current hdcp level: {}', drm_info['hdcp_level'])
        common.debug('Widevine CryptoSession max hdcp level supported: {}', drm_info['hdcp_level_max'])
        common.debug('Widevine CryptoSession algorithms: {}', self.crypto_session.GetPropertyString('algorithms'))

    def load_crypto_session(self, msl_data=None):
        if not msl_data:
            return
        self.keyset_id = base64.standard_b64decode(msl_data['key_set_id'])
        self.key_id = base64.standard_b64decode(msl_data['key_id'])
        self.hmac_key_id = base64.standard_b64decode(msl_data['hmac_key_id'])
        self.crypto_session.RestoreKeys(self.keyset_id)

    def __del__(self):
        self.crypto_session = None

    def key_request_data(self):
        """Return a key request dict"""
        # No key update supported -> remove existing keys
        self.crypto_session.RemoveKeys()
        key_request = self.crypto_session.GetKeyRequest(  # pylint: disable=assignment-from-none
            bytearray([10, 122, 0, 108, 56, 43]), 'application/xml', True, dict())

        if not key_request:
            raise MSLError('Widevine CryptoSession getKeyRequest failed!')

        common.debug('Widevine CryptoSession getKeyRequest successful. Size: {}', len(key_request))
        return [{
            'scheme': 'WIDEVINE',
            'keydata': {
                'keyrequest': base64.standard_b64encode(key_request).decode('utf-8')
            }
        }]

    def _provide_key_response(self, data):
        if not data:
            raise MSLError('Missing key response data')
        self.keyset_id = self.crypto_session.ProvideKeyResponse(bytearray(data))  # pylint: disable=assignment-from-none
        if not self.keyset_id:
            raise MSLError('Widevine CryptoSession provideKeyResponse failed')
        common.debug('Widevine CryptoSession provideKeyResponse successful')
        common.debug('keySetId: {}', self.keyset_id)
        self.keyset_id = self.keyset_id.encode('utf-8')

    def encrypt(self, plaintext, esn):  # pylint: disable=unused-argument
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        from os import urandom
        init_vector = bytearray(urandom(16))
        # Add PKCS5Padding
        pad = 16 - len(plaintext) % 16
        padded_data = plaintext + ''.join([chr(pad)] * pad)
        encrypted_data = self.crypto_session.Encrypt(bytearray(self.key_id),
                                                     bytearray(padded_data.encode('utf-8')),
                                                     init_vector)

        if not encrypted_data:
            raise MSLError('Widevine CryptoSession encrypt failed!')

        return json.dumps({
            'version': 1,
            'ciphertext': base64.standard_b64encode(encrypted_data).decode('utf-8'),
            'sha256': 'AA==',
            'keyid': base64.standard_b64encode(self.key_id).decode('utf-8'),
            # 'cipherspec' : 'AES/CBC/PKCS5Padding',
            'iv': base64.standard_b64encode(init_vector).decode('utf-8')
        })

    def decrypt(self, init_vector, ciphertext):
        """Decrypt a ciphertext"""
        decrypted_data = self.crypto_session.Decrypt(bytearray(self.key_id), bytearray(ciphertext),
                                                     bytearray(init_vector))
        if not decrypted_data:
            raise MSLError('Widevine CryptoSession decrypt failed!')

        # remove PKCS5Padding
        pad = decrypted_data[len(decrypted_data) - 1]
        return decrypted_data[:-pad].decode('utf-8')

    def sign(self, message):
        """Sign a message"""
        signature = self.crypto_session.Sign(bytearray(self.hmac_key_id),
                                             bytearray(message.encode('utf-8')))
        if not signature:
            raise MSLError('Widevine CryptoSession sign failed!')
        return base64.standard_b64encode(signature).decode('utf-8')

    def verify(self, message, signature):
        """Verify a message's signature"""
        return self.crypto_session.Verify(self.hmac_key_id, message, signature)

    def _init_keys(self, key_response_data):
        key_response = base64.standard_b64decode(
            key_response_data['keydata']['cdmkeyresponse'])
        self._provide_key_response(key_response)
        self.key_id = base64.standard_b64decode(
            key_response_data['keydata']['encryptionkeyid'])
        self.hmac_key_id = base64.standard_b64decode(
            key_response_data['keydata']['hmackeyid'])

    def _export_keys(self):
        return {
            'key_set_id': base64.standard_b64encode(self.keyset_id).decode('utf-8'),
            'key_id': base64.standard_b64encode(self.key_id).decode('utf-8'),
            'hmac_key_id': base64.standard_b64encode(self.hmac_key_id).decode('utf-8')
        }
