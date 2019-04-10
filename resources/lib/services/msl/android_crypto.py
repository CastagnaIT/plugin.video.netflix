# -*- coding: utf-8 -*-
"""Crypto handler for Android platforms"""
from __future__ import unicode_literals

from os import urandom
import base64
import json

import xbmcdrm

import resources.lib.common as common

from .base_crypto import MSLBaseCrypto
from .exceptions import MastertokenExpired
from .exceptions import MSLError


class AndroidMSLCrypto(MSLBaseCrypto):
    """Crypto handler for Android platforms"""
    def __init__(self, msl_data=None):
        # pylint: disable=broad-except
        try:
            self.crypto_session = xbmcdrm.CryptoSession(
                'edef8ba9-79d6-4ace-a3c8-27dcd51d21ed', 'AES/CBC/NoPadding',
                'HmacSHA256')
            common.debug('Widevine CryptoSession successful constructed')
        except Exception:
            import traceback
            common.error(traceback.format_exc())
            raise MSLError('Failed to construct Widevine CryptoSession')

        try:
            super(AndroidMSLCrypto, self).__init__(msl_data)
            self.keyset_id = base64.standard_b64decode(msl_data['key_set_id'])
            self.key_id = base64.standard_b64decode(msl_data['key_id'])
            self.hmac_key_id = base64.standard_b64decode(
                msl_data['hmac_key_id'])
            self.crypto_session.RestoreKeys(self.keyset_id)

        except MastertokenExpired as me:
            raise me
        except Exception:
            self.keyset_id = None
            self.key_id = None
            self.hmac_key_id = None

        common.debug('Widevine CryptoSession systemId: {}'
                     .format(
                         self.crypto_session.GetPropertyString('systemId')))
        common.debug('Widevine CryptoSession algorithms: {}'
                     .format(
                         self.crypto_session.GetPropertyString('algorithms')))

    def __del__(self):
        self.crypto_session = None

    def key_request_data(self):
        """Return a key request dict"""
        # No key update supported -> remove existing keys
        self.crypto_session.RemoveKeys()
        key_request = self.crypto_session.GetKeyRequest(
            bytes([10, 122, 0, 108, 56, 43]), 'application/xml', True, dict())

        if not key_request:
            raise MSLError('Widevine CryptoSession getKeyRequest failed!')

        common.log('Widevine CryptoSession getKeyRequest successful. Size: {}'
                   .format(len(key_request)))
        return [{
            'scheme': 'WIDEVINE',
            'keydata': {
                'keyrequest': base64.standard_b64encode(key_request)
            }
        }]

    def _provide_key_response(self, data):
        if not data:
            raise MSLError('Missing key response data')
        self.keyset_id = self.crypto_session.ProvideKeyResponse(data)
        if not self.keyset_id:
            raise MSLError('Widevine CryptoSession provideKeyResponse failed')
        common.debug('Widevine CryptoSession provideKeyResponse successful')
        common.debug('keySetId: {}'.format(self.keyset_id))

    def encrypt(self, plaintext, esn):
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        # pylint: disable=unused-argument
        init_vector = urandom(16)
        plaintext = plaintext.encode('utf-8')
        # Add PKCS5Padding
        pad = 16 - len(plaintext) % 16
        padded_data = plaintext + str('').join([chr(pad)] * pad)
        encrypted_data = self.crypto_session.Encrypt(self.key_id, padded_data,
                                                     init_vector)

        if not encrypted_data:
            raise MSLError('Widevine CryptoSession encrypt failed!')

        return json.dumps({
            'version': 1,
            'ciphertext': base64.standard_b64encode(encrypted_data),
            'sha256': 'AA==',
            'keyid': base64.standard_b64encode(self.key_id),
            # 'cipherspec' : 'AES/CBC/PKCS5Padding',
            'iv': base64.standard_b64encode(init_vector)
        })

    def decrypt(self, init_vector, ciphertext):
        """Decrypt a ciphertext"""
        decrypted_data = self.crypto_session.Decrypt(self.key_id, ciphertext,
                                                     init_vector)
        if not decrypted_data:
            raise MSLError('Widevine CryptoSession decrypt failed!')

        # remove PKCS5Padding
        pad = decrypted_data[len(decrypted_data) - 1]
        return decrypted_data[:-pad].decode('utf-8')

    def sign(self, message):
        """Sign a message"""
        signature = self.crypto_session.Sign(self.hmac_key_id, message)
        if not signature:
            raise MSLError('Widevine CryptoSession sign failed!')
        return base64.standard_b64encode(signature)

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
            'key_set_id': base64.standard_b64encode(self.keyset_id),
            'key_id': base64.standard_b64encode(self.key_id),
            'hmac_key_id': base64.standard_b64encode(self.hmac_key_id)
        }
