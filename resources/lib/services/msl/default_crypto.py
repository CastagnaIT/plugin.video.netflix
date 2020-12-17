# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2017 Trummerjo (original implementation module)
    Copyright (C) 2018 Caphm
    Crypto handler for non-Android platforms

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import base64
import json


try:  # The crypto package depends on the library installed (see Wiki)
    from Cryptodome.Random import get_random_bytes
    from Cryptodome.Hash import HMAC, SHA256
    from Cryptodome.Cipher import PKCS1_OAEP
    from Cryptodome.PublicKey import RSA
    from Cryptodome.Util import Padding
    from Cryptodome.Cipher import AES
except ImportError:
    from Crypto.Random import get_random_bytes
    from Crypto.Hash import HMAC, SHA256
    from Crypto.Cipher import PKCS1_OAEP
    from Crypto.PublicKey import RSA
    from Crypto.Util import Padding
    from Crypto.Cipher import AES

from resources.lib.common.exceptions import MSLError
from resources.lib.utils.logging import LOG
from .base_crypto import MSLBaseCrypto


class DefaultMSLCrypto(MSLBaseCrypto):
    """Crypto Handler for non-Android platforms"""

    def __init__(self):
        super().__init__()
        self.rsa_key = None
        self.encryption_key = None
        self.sign_key = None

    def load_crypto_session(self, msl_data=None):
        try:
            self.encryption_key = base64.standard_b64decode(
                msl_data['encryption_key'])
            self.sign_key = base64.standard_b64decode(
                msl_data['sign_key'])
            if not self.encryption_key or not self.sign_key:
                raise MSLError('Missing encryption_key or sign_key')
            self.rsa_key = RSA.importKey(
                base64.standard_b64decode(msl_data['rsa_key']))
        except Exception:  # pylint: disable=broad-except
            LOG.debug('Generating new RSA keys')
            self.rsa_key = RSA.generate(2048)
            self.encryption_key = None
            self.sign_key = None

    def key_request_data(self):
        """Return a key request dict"""
        public_key = base64.standard_b64encode(
            self.rsa_key.publickey().exportKey(format='DER'))
        return [{'scheme': 'ASYMMETRIC_WRAPPED',
                 'keydata': {
                     'publickey': public_key.decode('utf-8'),
                     'mechanism': 'JWK_RSA',
                     'keypairid': 'rsaKeypairId'
                 }}]

    def encrypt(self, plaintext, esn):
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        init_vector = get_random_bytes(16)
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, init_vector)
        ciphertext = base64.standard_b64encode(
            cipher.encrypt(Padding.pad(plaintext.encode('utf-8'), 16))).decode('utf-8')
        encryption_envelope = {
            'ciphertext': ciphertext,
            'keyid': '_'.join((esn, str(self.sequence_number))),
            'sha256': 'AA==',
            'iv': base64.standard_b64encode(init_vector).decode('utf-8')
        }
        return json.dumps(encryption_envelope)

    def decrypt(self, init_vector, ciphertext):
        """Decrypt a ciphertext"""
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, init_vector)
        return Padding.unpad(cipher.decrypt(ciphertext), 16)

    def sign(self, message):
        """Sign a message"""
        return base64.standard_b64encode(
            HMAC.new(self.sign_key, message.encode('utf-8'), SHA256).digest()).decode('utf-8')

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
            'encryption_key': base64.standard_b64encode(self.encryption_key).decode('utf-8'),
            'sign_key': base64.standard_b64encode(self.sign_key).decode('utf-8'),
            'rsa_key': base64.standard_b64encode(self.rsa_key.exportKey()).decode('utf-8')
        }


def _decrypt_key(encrypted_key, cipher):
    return _base64key_decode(json.loads(cipher.decrypt(encrypted_key))['k'])


def _base64key_decode(b64):
    padding = len(b64) % 4
    if padding != 0:
        b64 += '=' * (4 - padding)
    return base64.urlsafe_b64decode(b64.encode('utf8'))
