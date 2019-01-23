# -*- coding: utf-8 -*-
"""Crypto handler for non-Android platforms"""
from __future__ import unicode_literals

import json
import base64
from Cryptodome.Random import get_random_bytes
from Cryptodome.Hash import HMAC, SHA256
from Cryptodome.Cipher import PKCS1_OAEP
from Cryptodome.PublicKey import RSA
from Cryptodome.Util import Padding
from Cryptodome.Cipher import AES

from resources.lib.globals import g
import resources.lib.common as common

from .base_crypto import MSLBaseCrypto
from .exceptions import MastertokenExpired


class DefaultMSLCrypto(MSLBaseCrypto):
    """Crypto Handler for non-Android platforms"""
    def __init__(self, msl_data=None):
        # pylint: disable=broad-except
        try:
            super(DefaultMSLCrypto, self).__init__(msl_data)
            self.encryption_key = base64.standard_b64decode(
                msl_data['encryption_key'])
            self.sign_key = base64.standard_b64decode(
                msl_data['sign_key'])
            if not self.encryption_key or not self.sign_key:
                raise ValueError('Missing encryption_key or sign_key')
            self.rsa_key = RSA.importKey(
                base64.standard_b64decode(msl_data['rsa_key']))

        except MastertokenExpired as me:
            raise me
        except Exception:
            common.debug('Generating new RSA keys')
            self.rsa_key = RSA.generate(2048)
            self.encryption_key = None
            self.sign_key = None

    def key_request_data(self):
        """Return a key request dict"""
        public_key = base64.standard_b64encode(
            self.rsa_key.publickey().exportKey(format='DER'))
        return [{'scheme': 'ASYMMETRIC_WRAPPED',
                 'keydata': {
                     'publickey': public_key,
                     'mechanism': 'JWK_RSA',
                     'keypairid': 'superKeyPair'
                 }}]

    def encrypt(self, plaintext, esn):
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        init_vector = get_random_bytes(16)
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, init_vector)
        encryption_envelope = {
            'ciphertext': '',
            'keyid': '_'.join((esn, str(self.sequence_number))),
            'sha256': 'AA==',
            'iv': base64.standard_b64encode(init_vector)
        }
        encryption_envelope['ciphertext'] = base64.standard_b64encode(
            cipher.encrypt(Padding.pad(plaintext.encode('utf-8'), 16)))

        return json.dumps(encryption_envelope)

    def decrypt(self, init_vector, ciphertext):
        """Decrypt a ciphertext"""
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, init_vector)
        return Padding.unpad(cipher.decrypt(ciphertext), 16)

    def sign(self, message):
        """Sign a message"""
        return base64.standard_b64encode(
            HMAC.new(self.sign_key, message, SHA256).digest())

    def _init_keys(self, key_response_data):
        cipher = PKCS1_OAEP.new(self.rsa_key)
        encrypted_encryption_key = base64.standard_b64decode(
            key_response_data['keydata']['encryptionkey'])
        encrypted_sign_key = base64.standard_b64decode(
            key_response_data['keydata']['hmackey'])
        self.encryption_key = _decrypt_key(encrypted_encryption_key, cipher)
        self.sign_key = _decrypt_key(encrypted_sign_key, cipher)

    def _export_keys(self):
        return {
            'encryption_key': base64.standard_b64encode(self.encryption_key),
            'sign_key': base64.standard_b64encode(self.sign_key),
            'rsa_key': base64.standard_b64encode(self.rsa_key.exportKey())
        }


def _decrypt_key(encrypted_key, cipher):
    return _base64key_decode(json.loads(cipher.decrypt(encrypted_key))['k'])


def _base64key_decode(b64):
    padding = len(b64) % 4
    if padding != 0:
        b64 += '=' * (4 - padding)
    return base64.urlsafe_b64decode(b64.encode('utf8'))
