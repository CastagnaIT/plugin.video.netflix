# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H
"""Crypto handler for non-Android platforms"""
from __future__ import unicode_literals

import time
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

from .exceptions import MastertokenExpired


class MSLCrypto(object):
    """Crypto Handler for non-Android platforms"""
    def __init__(self, msl_data=None):
        # pylint: disable=broad-except
        try:
            self.encryption_key = base64.standard_b64decode(
                msl_data['encryption_key'])
            self.sign_key = base64.standard_b64decode(
                msl_data['sign_key'])
            if not self.encryption_key or not self.sign_key:
                raise ValueError('Missing encryption_key or sign_key')
            self.rsa_key = RSA.importKey(
                base64.standard_b64decode(msl_data['rsa_key']))
            self._set_mastertoken(msl_data['tokens']['mastertoken'])
            common.debug('Loaded crypto keys')
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

    def parse_key_response(self, headerdata):
        """Parse a key response and assign contained encryption_key and
        sign_key"""
        self._set_mastertoken(headerdata['keyresponsedata']['mastertoken'])
        cipher = PKCS1_OAEP.new(self.rsa_key)
        encrypted_encryption_key = base64.standard_b64decode(
            headerdata['keyresponsedata']['keydata']['encryptionkey'])
        encrypted_sign_key = base64.standard_b64decode(
            headerdata['keyresponsedata']['keydata']['hmackey'])
        self.encryption_key = _decrypt_key(encrypted_encryption_key, cipher)
        self.sign_key = _decrypt_key(encrypted_sign_key, cipher)
        self._save_msl_data()

    def encrypt(self, plaintext):
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        init_vector = get_random_bytes(16)
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, init_vector)
        encryption_envelope = {
            'ciphertext': '',
            'keyid': '_'.join((g.get_esn(), str(self.sequence_number))),
            'sha256': 'AA==',
            'iv': base64.standard_b64encode(init_vector)
        }
        encryption_envelope['ciphertext'] = base64.standard_b64encode(
            cipher.encrypt(Padding.pad(plaintext, 16)))

        return json.dumps(encryption_envelope)

    def decrypt(self, init_vector, data):
        """Decrypt a ciphertext"""
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, init_vector)
        return Padding.unpad(cipher.decrypt(data), 16)

    def sign(self, message):
        """Sign a message"""
        return base64.standard_b64encode(
            HMAC.new(self.sign_key, message, SHA256).digest())

    def _save_msl_data(self):
        """Save encryption keys and mastertoken to disk"""
        msl_data = {
            'tokens': {'mastertoken': self.mastertoken},
            'encryption_key': base64.standard_b64encode(self.encryption_key),
            'sign_key': base64.standard_b64encode(self.sign_key),
            'rsa_key': base64.standard_b64encode(self.rsa_key.exportKey())
        }
        common.save_file('msl_data.json', json.dumps(msl_data))
        common.debug('Successfully saved MSL data to disk')

    def _set_mastertoken(self, mastertoken):
        tokendata = json.loads(
            base64.standard_b64decode(mastertoken['tokendata']))
        remaining_ttl = (int(tokendata['expiration']) - time.time())
        if remaining_ttl / 60 / 60 >= 10:
            self.mastertoken = mastertoken
            self.sequence_number = tokendata.get('sequencenumber', 0)
        else:
            raise MastertokenExpired


def _decrypt_key(encrypted_key, cipher):
    return _base64key_decode(json.loads(cipher.decrypt(encrypted_key))['k'])


def _base64key_decode(payload):
    length = len(payload) % 4
    if length == 2:
        payload += '=='
    elif length == 3:
        payload += '='
    elif length != 0:
        raise ValueError('Invalid base64 string')
    return base64.urlsafe_b64decode(payload.encode('utf-8'))
