# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H
"""Proxy service to convert manifest and provide license data"""
from __future__ import unicode_literals

import re
import sys
import zlib
import gzip
import json
import time
import base64
import random
import uuid
from StringIO import StringIO
from datetime import datetime
import requests
import xml.etree.ElementTree as ET

from resources.lib.globals import g
import resources.lib.common as common

from .profiles import enabled_profiles
from .converter import convert_to_dash

#check if we are on Android
import subprocess
try:
    sdkversion = int(subprocess.check_output(
        ['/system/bin/getprop', 'ro.build.version.sdk']))
except:
    sdkversion = 0 

if sdkversion >= 18:
  from MSLMediaDrm import MSLMediaDrmCrypto as MSLCrypto
else:
    from .default_crypto import MSLCrypto as MSLCrypto

class MSLHandler(object):
    # Is a handshake already performed and the keys loaded
    handshake_performed = False
    last_drm_context = ''
    last_playback_context = ''
    current_message_id = 0
    session = requests.session()
    rndm = random.SystemRandom()
    tokens = []
    base_url = 'http://www.netflix.com/api/msl/NFCDCH-LX/cadmium/'
    endpoints = {
        'manifest': base_url + 'manifest',
        'license': base_url + 'license'
    }

    def __init__(self):
        # pylint: disable=broad-except
        try:
            msl_data = json.loads(common.load_file('msl_data.json'))
            self.crypto = MSLCrypto(msl_data)
        except Exception:
            self.crypto = MSLCrypto()
            self.perform_key_handshake()
        common.register_slot(
            signal=common.Signals.ESN_CHANGED,
            callback=self.perform_key_handshake)

    def load_manifest(self, viewable_id):
        """
        Loads the manifets for the given viewable_id and
        returns a mpd-XML-Manifest

        :param viewable_id: The id of of the viewable
        :return: MPD XML Manifest or False if no success
        """
        manifest_request_data = {
            'method': 'manifest',
            'lookupType': 'PREPARE',
            'viewableIds': [viewable_id],
            'profiles': enabled_profiles(),
            'drmSystem': 'widevine',
            'appId': '14673889385265',
            'sessionParams': {
                'pinCapableClient': False,
                'uiplaycontext': 'null'
            },
            'sessionId': '14673889385265',
            'trackId': 0,
            'flavor': 'PRE_FETCH',
            'secureUrls': False,
            'supportPreviewContent': True,
            'forceClearStreams': False,
            'languages': ['de-DE'],
            'clientVersion': '4.0004.899.011',
            'uiVersion': 'akira'
        }
        request_data = self.__generate_msl_request_data(manifest_request_data)
        common.debug(request_data)
        try:
            resp = self.session.post(self.endpoints['manifest'], request_data)
        except:
            resp = None
            exc = sys.exc_info()
            msg = '[MSL][POST] Error {} {}'
            common.log(msg.format(exc[0], exc[1]))

        if resp:
            try:
                # if the json() does not fail we have an error because
                # the manifest response is a chuncked json response
                resp.json()
                common.log(
                    msg='Error getting Manifest: ' + resp.text)
                return False
            except ValueError:
                # json() failed so parse the chunked response
                #common.log(
                #    msg='Got chunked Manifest Response: ' + resp.text)
                resp = self.__parse_chunked_msl_response(resp.text)
                #common.log(
                #    msg='Parsed chunked Response: ' + json.dumps(resp))
                data = self.__decrypt_payload_chunks(resp['payloads'])
                return self.__tranform_to_dash(data)
        return False

    def get_license(self, challenge, sid):
        """
        Requests and returns a license for the given challenge and sid
        :param challenge: The base64 encoded challenge
        :param sid: The sid paired to the challengew
        :return: Base64 representation of the licensekey or False unsuccessfull
        """
        license_request_data = {
            'method': 'license',
            'licenseType': 'STANDARD',
            'clientVersion': '4.0004.899.011',
            'uiVersion': 'akira',
            'languages': ['de-DE'],
            'playbackContextId': self.last_playback_context,
            'drmContextIds': [self.last_drm_context],
            'challenges': [{
                'dataBase64': challenge,
                'sessionId': sid
            }],
            'clientTime': int(time.time()),
            'xid': int((int(time.time()) + 0.1612) * 1000)

        }
        request_data = self.__generate_msl_request_data(license_request_data)

        try:
            resp = self.session.post(self.endpoints['license'], request_data)
        except:
            resp = None
            exc = sys.exc_info()
            common.log(
                msg='[MSL][POST] Error {} {}'.format(exc[0], exc[1]))

        if resp:
            try:
                # If is valid json the request for the licnese failed
                resp.json()
                common.log('Error getting license: '+resp.text)
                return False
            except ValueError:
                # json() failed so we have a chunked json response
                resp = self.__parse_chunked_msl_response(resp.text)
                data = self.__decrypt_payload_chunks(resp['payloads'])
                if data['success'] is True:
                    return data['result']['licenses'][0]['data']
                else:
                    common.log(
                        msg='Error getting license: ' + json.dumps(data))
                    return False
        return False

    def __decrypt_payload_chunks(self, payloadchunks):
        decrypted_payload = ''
        for chunk in payloadchunks:
            payloadchunk = json.JSONDecoder().decode(chunk)
            payload = payloadchunk.get('payload')
            decoded_payload = base64.standard_b64decode(payload)
            encryption_envelope = json.JSONDecoder().decode(decoded_payload)
            # Decrypt the text
            plaintext = self.crypto.decrypt(base64.standard_b64decode(encryption_envelope['iv']),
              base64.standard_b64decode(encryption_envelope.get('ciphertext')))
            # unpad the plaintext
            plaintext = json.JSONDecoder().decode(plaintext)
            data = plaintext.get('data')

            # uncompress data if compressed
            if plaintext.get('compressionalgo') == 'GZIP':
                decoded_data = base64.standard_b64decode(data)
                data = zlib.decompress(decoded_data, 16 + zlib.MAX_WBITS)
            else:
                data = base64.standard_b64decode(data)
            decrypted_payload += data

        decrypted_payload = json.JSONDecoder().decode(decrypted_payload)[1]['payload']['data']
        decrypted_payload = base64.standard_b64decode(decrypted_payload)
        return json.JSONDecoder().decode(decrypted_payload)

    def __tranform_to_dash(self, manifest):
        common.save_file('manifest.json', json.dumps(manifest))
        manifest = manifest['result']['viewables'][0]
        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']
        return convert_to_dash(manifest)

    def __get_base_url(self, urls):
        for key in urls:
            return urls[key]

    def __parse_chunked_msl_response(self, message):
        header = message.split('}}')[0] + '}}'
        payloads = re.split(',\"signature\":\"[0-9A-Za-z=/+]+\"}', message.split('}}')[1])
        payloads = [x + '}' for x in payloads][:-1]

        return {
            'header': header,
            'payloads': payloads
        }

    def __generate_msl_request_data(self, data):
        #self.__load_msl_data()
        mslheader = self.__generate_msl_header()
        common.debug('Plaintext headerdata: {}'.format(mslheader))
        header_encryption_envelope = self.crypto.encrypt(mslheader)
        headerdata = base64.standard_b64encode(header_encryption_envelope)
        header = {
            'headerdata': headerdata,
            'signature': self.crypto.sign(header_encryption_envelope),
            'mastertoken': self.crypto.mastertoken,
        }

        # Serialize the given Data
        raw_marshalled_data = json.dumps(data)
        marshalled_data = raw_marshalled_data.replace('"', '\\"')
        serialized_data = '[{},{"headers":{},"path":"/cbp/cadmium-13"'
        serialized_data += ',"payload":{"data":"'
        serialized_data += marshalled_data
        serialized_data += '"},"query":""}]\n'
        common.debug('Serialized data: {}'.format(serialized_data))
        compressed_data = self.__compress_data(serialized_data)

        # Create FIRST Payload Chunks
        first_payload = {
            'messageid': self.current_message_id,
            'data': compressed_data,
            'compressionalgo': 'GZIP',
            'sequencenumber': 1,
            'endofmsg': True
        }
        common.debug('Plaintext Payload: {}'.format(first_payload))
        first_payload_encryption_envelope = self.crypto.encrypt(json.dumps(first_payload))
        payload = base64.standard_b64encode(first_payload_encryption_envelope)
        first_payload_chunk = {
            'payload': payload,
            'signature': self.crypto.sign(first_payload_encryption_envelope),
        }
        request_data = json.dumps(header) + json.dumps(first_payload_chunk)
        return request_data

    def __compress_data(self, data):
        # GZIP THE DATA
        out = StringIO()
        with gzip.GzipFile(fileobj=out, mode="w") as f:
            f.write(data)
        return base64.standard_b64encode(out.getvalue())

    def __generate_msl_header(
            self,
            is_handshake=False,
            is_key_request=False,
            compressionalgo='GZIP',
            encrypt=True):
        """
        Function that generates a MSL header dict
        :return: The base64 encoded JSON String of the header
        """
        self.current_message_id = self.rndm.randint(0, pow(2, 52))
        esn = g.get_esn()

        # Add compression algo if not empty
        compression_algos = [compressionalgo] if compressionalgo != '' else []

        header_data = {
            'sender': esn,
            'handshake': is_handshake,
            'nonreplayable': False,
            'capabilities': {
                'languages': ['en-US'],
                'compressionalgos': compression_algos
            },
            'recipient': 'Netflix',
            'renewable': True,
            'messageid': self.current_message_id,
            'timestamp': 1467733923
        }

        # If this is a keyrequest act diffrent then other requests
        if is_key_request:
            header_data['keyrequestdata'] = self.crypto.get_key_request()
        else:
            if 'usertoken' in self.tokens:
                pass
            else:
                account = common.get_credentials()
                # Auth via email and password
                header_data['userauthdata'] = {
                    'scheme': 'EMAIL_PASSWORD',
                    'authdata': {
                        'email': account['email'],
                        'password': account['password']
                    }
                }

        return json.dumps(header_data)

    def perform_key_handshake(self):
        esn = g.get_esn()
        common.log('perform_key_handshake: esn:' + esn)

        if not esn:
          return False

        header = self.__generate_msl_header(
            is_key_request=True,
            is_handshake=True,
            compressionalgo='',
            encrypt=False)

        request = {
            'entityauthdata': {
                'scheme': 'NONE',
                'authdata': {
                    'identity': esn
                }
            },
            'headerdata': base64.standard_b64encode(header),
            'signature': '',
        }
        #common.log('Key Handshake Request:')
        #common.log(json.dumps(request))

        try:
            resp = self.session.post(
                url=self.endpoints['manifest'],
                data=json.dumps(request, sort_keys=True))
        except:
            resp = None
            exc = sys.exc_info()
            common.log(
                msg='[MSL][POST] Error {} {}'.format(exc[0], exc[1]))

        if resp and resp.status_code == 200:
            resp = resp.json()
            if 'errordata' in resp:
                common.log('Key Exchange failed')
                common.log(
                    msg=base64.standard_b64decode(resp['errordata']))
                return False
            base_head = base64.standard_b64decode(resp['headerdata'])

            headerdata=json.JSONDecoder().decode(base_head)
            self.crypto.parse_key_response(headerdata)
        else:
            common.log('Key Exchange failed')
            common.log(resp.text)
