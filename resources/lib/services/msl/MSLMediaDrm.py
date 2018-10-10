from __future__ import unicode_literals

from os import urandom
import json
import base64
import xbmcdrm
import pprint

import resources.lib.common as common

class MSLMediaDrmCrypto:

    def __init__(self, kodi_helper):
        self.kodi_helper = kodi_helper

        self.keySetId = None
        self.keyId = None
        self.hmacKeyId = None

        try:
            self.cryptoSession = xbmcdrm.CryptoSession('edef8ba9-79d6-4ace-a3c8-27dcd51d21ed',
                                                       'AES/CBC/NoPadding', 'HmacSHA256')
            common.log('Widevine CryptoSession successful constructed')
        except:
            self.cryptoSession = None
            return

        self.systemId = self.cryptoSession.GetPropertyString('systemId')
        common.log('Widevine CryptoSession systemId: {}'.format(self.systemId))

        algorithms = self.cryptoSession.GetPropertyString('algorithms')
        common.log('Widevine CryptoSession algorithms: {}'.format(algorithms))

    def __del__(self):
        self.cryptoSession = None

    def __getKeyRequest(self, data):
         #No key update supported -> remove existing keys
         self.cryptoSession.RemoveKeys()
         keyRequest = self.cryptoSession.GetKeyRequest(data, 'application/xml', True, dict())
         if keyRequest:
             common.log('Widevine CryptoSession getKeyRequest successful with size: {}'.format(len(keyRequest)))
             return keyRequest
         else:
             common.log('Widevine CryptoSession getKeyRequest failed!')

    def __provideKeyResponse(self, data):
        if len(data) == 0:
            return False

        self.keySetId = self.cryptoSession.ProvideKeyResponse(data)

        if self.keySetId:
            common.log('Widevine CryptoSession provideKeyResponse successful, keySetId: {}'.format(self.keySetId))
        else:
            common.log('Widevine CryptoSession provideKeyResponse failed!')

        return self.keySetId != None

    def toDict(self):
        common.log('Provide Widevine keys to dict')
        data = {
            "key_set_id": base64.standard_b64encode(self.keySetId),
            'key_id': base64.standard_b64encode(self.keyId),
            'hmac_key_id': base64.standard_b64encode(self.hmacKeyId)
        }
        return data

    def fromDict(self, msl_data):
        need_handshake = False

        if not self.cryptoSession:
             return False

        try:
            common.log('Parsing Widevine keys from Dict')
            self.keySetId = base64.standard_b64decode(msl_data['key_set_id'])
            self.keyId = base64.standard_b64decode(msl_data['key_id'])
            self.hmacKeyId = base64.standard_b64decode(msl_data['hmac_key_id'])

            self.cryptoSession.RestoreKeys(self.keySetId)

        except:
            need_handshake = True

        return need_handshake

    def get_key_request(self):
        drmKeyRequest = self.__getKeyRequest(bytes([10, 122, 0, 108, 56, 43]))

        key_request = [{
        'scheme': 'WIDEVINE',
        'keydata': {
            'keyrequest': base64.standard_b64encode(drmKeyRequest)
        }
        }]

        return key_request

    def parse_key_response(self, headerdata):
        # Init Decryption
        key_resonse = base64.standard_b64decode(headerdata['keyresponsedata']['keydata']['cdmkeyresponse'])

        if not self.__provideKeyResponse(key_resonse):
            return

        self.keyId = base64.standard_b64decode(headerdata['keyresponsedata']['keydata']['encryptionkeyid'])
        self.hmacKeyId = base64.standard_b64decode(headerdata['keyresponsedata']['keydata']['hmackeyid'])

    def decrypt(self, iv, data):
        decrypted = self.cryptoSession.Decrypt(self.keyId, data, iv)

        if decrypted:
            common.log('Widevine CryptoSession decrypt successful: {} bytes returned'.format(len(decrypted)))

            # remove PKCS5Padding
            pad = decrypted[len(decrypted) - 1]

            return decrypted[:-pad].decode('utf-8')
        else:
         common.log('Widevine CryptoSession decrypt failed!')

    def encrypt(self, data, esn, sequence_number):

        iv = urandom(16)

        # Add PKCS5Padding
        pad = 16 - len(data) % 16
        newData = data + ''.join([chr(pad)] * pad)

        encrypted = self.cryptoSession.Encrypt(self.keyId, newData, iv)

        if encrypted:
            common.log('Widevine CryptoSession encrypt successful: {} bytes returned'.format(len(encrypted)))

            encryption_envelope = {
                'version' : 1,
                'ciphertext': base64.standard_b64encode(encrypted),
                'sha256': 'AA==',
                'keyid': base64.standard_b64encode(self.keyId),
                #'cipherspec' : 'AES/CBC/PKCS5Padding',
                'iv': base64.standard_b64encode(iv)
            }
            return encryption_envelope
        else:
         common.log('Widevine CryptoSession encrypt failed!')

    def sign(self, message):
        signature = self.cryptoSession.Sign(self.hmacKeyId, message)
        if signature:
            common.log('Widevine CryptoSession sign success: length: {}'.format(len(signature)))
            return signature
        else:
            common.log('Widevine CryptoSession sign failed!')

    def verify(self, message, signature):
        return self.cryptoSession.Verify(self.hmacKeyId, message, signature)
