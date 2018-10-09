# pylint: skip-file
# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H

from Cryptodome.Random import get_random_bytes
from Cryptodome.Hash import HMAC, SHA256
from Cryptodome.Cipher import PKCS1_OAEP
from Cryptodome.PublicKey import RSA
from Cryptodome.Util import Padding
from Cryptodome.Cipher import AES
import json
import base64


class MSLCrypto():

    def __init__(self, kodi_helper):
        self.kodi_helper = kodi_helper
        self.encryption_key = None
        self.sign_key = None

    def __init_generate_rsa_keys(self):
        self.kodi_helper.log(msg='Create new RSA Keys')
        # Create new Key Pair and save
        self.rsa_key = RSA.generate(2048)

    @staticmethod
    def __base64key_decode(payload):
        l = len(payload) % 4
        if l == 2:
            payload += '=='
        elif l == 3:
            payload += '='
        elif l != 0:
            raise ValueError('Invalid base64 string')
        return base64.urlsafe_b64decode(payload.encode('utf-8'))

    def toDict(self):
        self.kodi_helper.log(msg='Provide RSA Keys to dict')
        # Get the DER Base64 of the keys
        encrypted_key = self.rsa_key.exportKey()

        data = {
            "encryption_key": base64.standard_b64encode(self.encryption_key),
            'sign_key': base64.standard_b64encode(self.sign_key),
            'rsa_key': base64.standard_b64encode(encrypted_key)
        }
        return data

    def fromDict(self, msl_data):
        need_handshake = False
        rsa_key = None

        try:
            self.kodi_helper.log(msg='Parsing RSA Keys from Dict')
            self.encryption_key = base64.standard_b64decode(msl_data['encryption_key'])
            self.sign_key = base64.standard_b64decode(msl_data['sign_key'])
            rsa_key = base64.standard_b64decode(msl_data['rsa_key'])
            self.rsa_key = RSA.importKey(rsa_key)
        except:
            need_handshake = True

        if not rsa_key:
            need_handshake = True
            self.__init_generate_rsa_keys()

        if not (self.encryption_key and self.sign_key):
            need_handshake = True

        return need_handshake

    def get_key_request(self):
        raw_key = self.rsa_key.publickey().exportKey(format='DER')
        public_key = base64.standard_b64encode(raw_key)

        key_request = [{
        'scheme': 'ASYMMETRIC_WRAPPED',
        'keydata': {
            'publickey': public_key,
            'mechanism': 'JWK_RSA',
            'keypairid': 'superKeyPair'
        }
        }]
        return key_request

    def parse_key_response(self, headerdata):
        # Init Decryption
        enc_key = headerdata['keyresponsedata']['keydata']['encryptionkey']
        hmac_key = headerdata['keyresponsedata']['keydata']['hmackey']
        encrypted_encryption_key = base64.standard_b64decode(enc_key)
        encrypted_sign_key = base64.standard_b64decode(hmac_key)
        cipher_rsa = PKCS1_OAEP.new(self.rsa_key)

        # Decrypt encryption key
        cipher_raw = cipher_rsa.decrypt(encrypted_encryption_key)
        encryption_key_data = json.JSONDecoder().decode(cipher_raw)
        self.encryption_key = self.__base64key_decode(encryption_key_data['k'])

        # Decrypt sign key
        sign_key_raw = cipher_rsa.decrypt(encrypted_sign_key)
        sign_key_data = json.JSONDecoder().decode(sign_key_raw)
        self.sign_key = self.__base64key_decode(sign_key_data['k'])

    def decrypt(self, iv, data):
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        return Padding.unpad(cipher.decrypt(data), 16)

    def encrypt(self, data, esn, sequence_number):
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        iv = get_random_bytes(16)
        encryption_envelope = {
                'ciphertext': '',
                'keyid': esn + '_' + str(sequence_number),
                'sha256': 'AA==',
                'iv': base64.standard_b64encode(iv)
        }
        # Padd the plaintext
        plaintext = Padding.pad(data, 16)
        # Encrypt the text
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        citext = cipher.encrypt(plaintext)
        encryption_envelope['ciphertext'] = base64.standard_b64encode(citext)

        return encryption_envelope;

    def sign(self, message):
        return HMAC.new(self.sign_key, message, SHA256).digest()