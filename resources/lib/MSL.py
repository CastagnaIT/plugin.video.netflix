# pylint: skip-file
# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H

import re
import sys
import zlib
import gzip
import json
import time
import base64
import random
from Cryptodome.Random import get_random_bytes
from Cryptodome.Hash import HMAC, SHA256
from Cryptodome.Cipher import PKCS1_OAEP
from Cryptodome.PublicKey import RSA
from Cryptodome.Util import Padding
from Cryptodome.Cipher import AES
from StringIO import StringIO
from datetime import datetime
import xbmcvfs
import requests
import xml.etree.ElementTree as ET


def base64key_decode(payload):
    l = len(payload) % 4
    if l == 2:
        payload += '=='
    elif l == 3:
        payload += '='
    elif l != 0:
        raise ValueError('Invalid base64 string')
    return base64.urlsafe_b64decode(payload.encode('utf-8'))


class MSL(object):
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

    def __init__(self, kodi_helper):
        """
        The Constructor checks for already existing crypto Keys.
        If they exist it will load the existing keys
        """
        self.kodi_helper = kodi_helper
        try:
            xbmcvfs.mkdir(path=self.kodi_helper.msl_data_path)
        except OSError:
            pass

        if self.file_exists(self.kodi_helper.msl_data_path, 'msl_data.json'):
            self.init_msl_data()
        elif self.file_exists(self.kodi_helper.msl_data_path, 'rsa_key.bin'):
            self.init_rsa_keys()
        else:
            self.init_generate_rsa_keys()

    def init_msl_data(self):
        self.kodi_helper.log(msg='MSL Data exists. Use old Tokens.')
        self.__load_msl_data()
        self.handshake_performed = True

    def init_rsa_keys(self):
        self.kodi_helper.log(msg='RSA Keys do already exist load old ones')
        self.__load_rsa_keys()
        if self.kodi_helper.get_esn():
            self.__perform_key_handshake()

    def init_generate_rsa_keys(self):
            self.kodi_helper.log(msg='Create new RSA Keys')
            # Create new Key Pair and save
            self.rsa_key = RSA.generate(2048)
            self.__save_rsa_keys()
            if self.kodi_helper.get_esn():
                self.__perform_key_handshake()

    def perform_key_handshake(self):
        self.__perform_key_handshake()

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
            'profiles': [
                # Video
                "playready-h264bpl30-dash",
                "playready-h264mpl30-dash",
                "playready-h264mpl31-dash",
                "playready-h264mpl40-dash",

                # Audio
                'heaac-2-dash',

                # Subtiltes
                # 'dfxp-ls-sdh',
                'simplesdh',
                # 'nflx-cmisc',

                # Unkown
                'BIF240',
                'BIF320'
            ],
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

        # add hevc profiles if setting is set
        if self.kodi_helper.use_hevc() is True:
            hevc = 'hevc-main-'
            main10 = 'hevc-main10-'
            prk = 'dash-cenc-prk'
            cenc = 'dash-cenc'
            ctl = 'dash-cenc-tl'
            hdr = 'hevc-hdr-main10-'
            dv = 'hevc-dv-main10-'
            dv5 = 'hevc-dv5-main10-'
            manifest_request_data['profiles'].append(main10 + 'L41-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L50-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L51-' + cenc)
            manifest_request_data['profiles'].append(hevc + 'L30-' + cenc)
            manifest_request_data['profiles'].append(hevc + 'L31-' + cenc)
            manifest_request_data['profiles'].append(hevc + 'L40-' + cenc)
            manifest_request_data['profiles'].append(hevc + 'L41-' + cenc)
            manifest_request_data['profiles'].append(hevc + 'L50-' + cenc)
            manifest_request_data['profiles'].append(hevc + 'L51-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L30-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L31-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L40-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L41-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L50-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L51-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L30-' + prk)
            manifest_request_data['profiles'].append(main10 + 'L31-' + prk)
            manifest_request_data['profiles'].append(main10 + 'L40-' + prk)
            manifest_request_data['profiles'].append(main10 + 'L41-' + prk)
            manifest_request_data['profiles'].append(hevc + 'L30-L31-' + ctl)
            manifest_request_data['profiles'].append(hevc + 'L31-L40-' + ctl)
            manifest_request_data['profiles'].append(hevc + 'L40-L41-' + ctl)
            manifest_request_data['profiles'].append(hevc + 'L50-L51-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L30-L31-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L31-L40-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L40-L41-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L50-L51-' + ctl)
            manifest_request_data['profiles'].append(dv + 'L30-' + cenc)
            manifest_request_data['profiles'].append(dv + 'L31-' + cenc)
            manifest_request_data['profiles'].append(dv + 'L40-' + cenc)
            manifest_request_data['profiles'].append(dv + 'L41-' + cenc)
            manifest_request_data['profiles'].append(dv + 'L50-' + cenc)
            manifest_request_data['profiles'].append(dv + 'L51-' + cenc)
            manifest_request_data['profiles'].append(dv5 + 'L30-' + prk)
            manifest_request_data['profiles'].append(dv5 + 'L31-' + prk)
            manifest_request_data['profiles'].append(dv5 + 'L40-' + prk)
            manifest_request_data['profiles'].append(dv5 + 'L41-' + prk)
            manifest_request_data['profiles'].append(dv5 + 'L50-' + prk)
            manifest_request_data['profiles'].append(dv5 + 'L51-' + prk)
            manifest_request_data['profiles'].append(hdr + 'L30-' + cenc)
            manifest_request_data['profiles'].append(hdr + 'L31-' + cenc)
            manifest_request_data['profiles'].append(hdr + 'L40-' + cenc)
            manifest_request_data['profiles'].append(hdr + 'L41-' + cenc)
            manifest_request_data['profiles'].append(hdr + 'L50-' + cenc)
            manifest_request_data['profiles'].append(hdr + 'L51-' + cenc)
            manifest_request_data['profiles'].append(hdr + 'L30-' + prk)
            manifest_request_data['profiles'].append(hdr + 'L31-' + prk)
            manifest_request_data['profiles'].append(hdr + 'L40-' + prk)
            manifest_request_data['profiles'].append(hdr + 'L41-' + prk)
            manifest_request_data['profiles'].append(hdr + 'L50-' + prk)
            manifest_request_data['profiles'].append(hdr + 'L51-' + prk)

        # Check if dolby sound is enabled and add to profles
        if self.kodi_helper.get_dolby_setting():
            manifest_request_data['profiles'].append('ddplus-2.0-dash')
            manifest_request_data['profiles'].append('ddplus-5.1-dash')

        request_data = self.__generate_msl_request_data(manifest_request_data)

        try:
            resp = self.session.post(self.endpoints['manifest'], request_data)
        except:
            resp = None
            exc = sys.exc_info()
            msg = '[MSL][POST] Error {} {}'
            self.kodi_helper.log(msg=msg.format(exc[0], exc[1]))

        if resp:
            try:
                # if the json() does not fail we have an error because
                # the manifest response is a chuncked json response
                resp.json()
                self.kodi_helper.log(
                    msg='Error getting Manifest: ' + resp.text)
                return False
            except ValueError:
                # json() failed so parse the chunked response
                self.kodi_helper.log(
                    msg='Got chunked Manifest Response: ' + resp.text)
                resp = self.__parse_chunked_msl_response(resp.text)
                self.kodi_helper.log(
                    msg='Parsed chunked Response: ' + json.dumps(resp))
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
            self.kodi_helper.log(
                msg='[MSL][POST] Error {} {}'.format(exc[0], exc[1]))

        if resp:
            try:
                # If is valid json the request for the licnese failed
                resp.json()
                self.kodi_helper.log(msg='Error getting license: '+resp.text)
                return False
            except ValueError:
                # json() failed so we have a chunked json response
                resp = self.__parse_chunked_msl_response(resp.text)
                data = self.__decrypt_payload_chunks(resp['payloads'])
                if data['success'] is True:
                    return data['result']['licenses'][0]['data']
                else:
                    self.kodi_helper.log(
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
            cipher = AES.new(
                self.encryption_key,
                AES.MODE_CBC,
                base64.standard_b64decode(encryption_envelope['iv']))
            ciphertext = encryption_envelope.get('ciphertext')
            plaintext = cipher.decrypt(base64.standard_b64decode(ciphertext))
            # unpad the plaintext
            plaintext = json.JSONDecoder().decode(Padding.unpad(plaintext, 16))
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

        self.save_file(
            msl_data_path=self.kodi_helper.msl_data_path,
            filename='manifest.json',
            content=json.dumps(manifest))
        manifest = manifest['result']['viewables'][0]

        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']

        # Check for pssh
        pssh = ''
        if 'psshb64' in manifest:
            if len(manifest['psshb64']) >= 1:
                pssh = manifest['psshb64'][0]

        seconds = manifest['runtime']/1000
        init_length = seconds / 2 * 12 + 20*1000
        duration = "PT"+str(seconds)+".00S"

        root = ET.Element('MPD')
        root.attrib['xmlns'] = 'urn:mpeg:dash:schema:mpd:2011'
        root.attrib['xmlns:cenc'] = 'urn:mpeg:cenc:2013'
        root.attrib['mediaPresentationDuration'] = duration

        period = ET.SubElement(root, 'Period', start='PT0S', duration=duration)

        # One Adaption Set for Video
        for video_track in manifest['videoTracks']:
            video_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                mimeType='video/mp4',
                contentType="video")
            # Content Protection
            protection = ET.SubElement(
                parent=video_adaption_set,
                tag='ContentProtection',
                schemeIdUri='urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED')

            ET.SubElement(
                parent=protection,
                tag='widevine:license',
                robustness_level='HW_SECURE_CODECS_REQUIRED')

            if pssh is not '':
                ET.SubElement(protection, 'cenc:pssh').text = pssh

            for downloadable in video_track['downloadables']:

                codec = 'h264'
                if 'hevc' in downloadable['contentProfile']:
                    codec = 'hevc'

                hdcp_versions = '0.0'
                for hdcp in downloadable['hdcpVersions']:
                    if hdcp != 'none':
                        hdcp_versions = hdcp

                rep = ET.SubElement(
                    parent=video_adaption_set,
                    tag='Representation',
                    width=str(downloadable['width']),
                    height=str(downloadable['height']),
                    bandwidth=str(downloadable['bitrate']*1024),
                    hdcp=hdcp_versions,
                    nflxContentProfile=str(downloadable['contentProfile']),
                    codecs=codec,
                    mimeType='video/mp4')

                # BaseURL
                base_url = self.__get_base_url(downloadable['urls'])
                ET.SubElement(rep, 'BaseURL').text = base_url
                # Init an Segment block
                segment_base = ET.SubElement(
                    parent=rep,
                    tag='SegmentBase',
                    indexRange='0-' + str(init_length),
                    indexRangeExact='true')
                ET.SubElement(
                    parent=segment_base,
                    tag='Initialization',
                    range='0-' + str(init_length))

        # Multiple Adaption Set for audio
        for audio_track in manifest['audioTracks']:
            impaired = 'false'
            if audio_track.get('trackType') != 'ASSISTIVE':
                impaired = 'true'
            audio_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                lang=audio_track['bcp47'],
                contentType='audio',
                mimeType='audio/mp4',
                impaired=impaired)
            for downloadable in audio_track['downloadables']:
                codec = 'aac'
                self.kodi_helper.log(msg=downloadable)
                is_dplus2 = downloadable['contentProfile'] == 'ddplus-2.0-dash'
                is_dplus5 = downloadable['contentProfile'] == 'ddplus-5.1-dash'
                if is_dplus2 or is_dplus5:
                    codec = 'ec-3'
                self.kodi_helper.log(msg='codec is: ' + codec)
                rep = ET.SubElement(
                    parent=audio_adaption_set,
                    tag='Representation',
                    codecs=codec,
                    bandwidth=str(downloadable['bitrate']*1024),
                    mimeType='audio/mp4')

                # AudioChannel Config
                uri = 'urn:mpeg:dash:23003:3:audio_channel_configuration:2011'
                ET.SubElement(
                    parent=rep,
                    tag='AudioChannelConfiguration',
                    schemeIdUri=uri,
                    value=str(audio_track.get('channelsCount')))

                # BaseURL
                base_url = self.__get_base_url(downloadable['urls'])
                ET.SubElement(rep, 'BaseURL').text = base_url
                # Index range
                segment_base = ET.SubElement(
                    parent=rep,
                    tag='SegmentBase',
                    indexRange='0-' + str(init_length),
                    indexRangeExact='true')
                ET.SubElement(
                    parent=segment_base,
                    tag='Initialization',
                    range='0-' + str(init_length))

        # Multiple Adaption Sets for subtiles
        for text_track in manifest.get('textTracks'):
            is_downloadables = 'downloadables' not in text_track
            if is_downloadables or text_track.get('downloadables') is None:
                continue
            subtiles_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                lang=text_track.get('bcp47'),
                codecs='stpp',
                contentType='text',
                mimeType='application/ttml+xml')
            for downloadable in text_track['downloadables']:
                rep = ET.SubElement(
                    parent=subtiles_adaption_set,
                    tag='Representation',
                    nflxProfile=downloadable.get('contentProfile'))
                base_url = self.__get_base_url(downloadable['urls'])
                ET.SubElement(rep, 'BaseURL').text = base_url

        xml = ET.tostring(root, encoding='utf-8', method='xml')
        xml = xml.replace('\n', '').replace('\r', '')
        return xml

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
        self.__load_msl_data()
        header_encryption_envelope = self.__encrypt(
            plaintext=self.__generate_msl_header())
        headerdata = base64.standard_b64encode(header_encryption_envelope)
        header = {
            'headerdata': headerdata,
            'signature': self.__sign(header_encryption_envelope),
            'mastertoken': self.mastertoken,
        }

        # Serialize the given Data
        raw_marshalled_data = json.dumps(data)
        marshalled_data = raw_marshalled_data.replace('"', '\\"')
        serialized_data = '[{},{"headers":{},"path":"/cbp/cadmium-13"'
        serialized_data += ',"payload":{"data":"'
        serialized_data += marshalled_data
        serialized_data += '"},"query":""}]\n'

        compressed_data = self.__compress_data(serialized_data)

        # Create FIRST Payload Chunks
        first_payload = {
            'messageid': self.current_message_id,
            'data': compressed_data,
            'compressionalgo': 'GZIP',
            'sequencenumber': 1,
            'endofmsg': True
        }
        first_payload_encryption_envelope = self.__encrypt(
            plaintext=json.dumps(first_payload))
        payload = base64.standard_b64encode(first_payload_encryption_envelope)
        first_payload_chunk = {
            'payload': payload,
            'signature': self.__sign(first_payload_encryption_envelope),
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
        esn = self.kodi_helper.get_esn()

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
            raw_key = self.rsa_key.publickey().exportKey(format='DER')
            public_key = base64.standard_b64encode(raw_key)
            header_data['keyrequestdata'] = [{
                'scheme': 'ASYMMETRIC_WRAPPED',
                'keydata': {
                    'publickey': public_key,
                    'mechanism': 'JWK_RSA',
                    'keypairid': 'superKeyPair'
                }
            }]
        else:
            if 'usertoken' in self.tokens:
                pass
            else:
                account = self.kodi_helper.get_credentials()
                # Auth via email and password
                header_data['userauthdata'] = {
                    'scheme': 'EMAIL_PASSWORD',
                    'authdata': {
                        'email': account['email'],
                        'password': account['password']
                    }
                }

        return json.dumps(header_data)

    def __encrypt(self, plaintext):
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        esn = self.kodi_helper.get_esn()

        iv = get_random_bytes(16)
        encryption_envelope = {
            'ciphertext': '',
            'keyid': esn + '_' + str(self.sequence_number),
            'sha256': 'AA==',
            'iv': base64.standard_b64encode(iv)
        }
        # Padd the plaintext
        plaintext = Padding.pad(plaintext, 16)
        # Encrypt the text
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        citext = cipher.encrypt(plaintext)
        encryption_envelope['ciphertext'] = base64.standard_b64encode(citext)
        return json.dumps(encryption_envelope)

    def __sign(self, text):
        """
        Calculates the HMAC signature for the given
        text with the current sign key and SHA256

        :param text:
        :return: Base64 encoded signature
        """
        signature = HMAC.new(self.sign_key, text, SHA256).digest()
        return base64.standard_b64encode(signature)

    def __perform_key_handshake(self):
        header = self.__generate_msl_header(
            is_key_request=True,
            is_handshake=True,
            compressionalgo='',
            encrypt=False)
        esn = self.kodi_helper.get_esn()

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
        self.kodi_helper.log(msg='Key Handshake Request:')
        self.kodi_helper.log(msg=json.dumps(request))

        try:
            resp = self.session.post(
                url=self.endpoints['manifest'],
                data=json.dumps(request, sort_keys=True))
        except:
            resp = None
            exc = sys.exc_info()
            self.kodi_helper.log(
                msg='[MSL][POST] Error {} {}'.format(exc[0], exc[1]))

        if resp and resp.status_code == 200:
            resp = resp.json()
            if 'errordata' in resp:
                self.kodi_helper.log(msg='Key Exchange failed')
                self.kodi_helper.log(
                    msg=base64.standard_b64decode(resp['errordata']))
                return False
            base_head = base64.standard_b64decode(resp['headerdata'])
            self.__parse_crypto_keys(
                headerdata=json.JSONDecoder().decode(base_head))
        else:
            self.kodi_helper.log(msg='Key Exchange failed')
            self.kodi_helper.log(msg=resp.text)

    def __parse_crypto_keys(self, headerdata):
        self.__set_master_token(headerdata['keyresponsedata']['mastertoken'])
        # Init Decryption
        enc_key = headerdata['keyresponsedata']['keydata']['encryptionkey']
        hmac_key = headerdata['keyresponsedata']['keydata']['hmackey']
        encrypted_encryption_key = base64.standard_b64decode(enc_key)
        encrypted_sign_key = base64.standard_b64decode(hmac_key)
        cipher_rsa = PKCS1_OAEP.new(self.rsa_key)

        # Decrypt encryption key
        cipher_raw = cipher_rsa.decrypt(encrypted_encryption_key)
        encryption_key_data = json.JSONDecoder().decode(cipher_raw)
        self.encryption_key = base64key_decode(encryption_key_data['k'])

        # Decrypt sign key
        sign_key_raw = cipher_rsa.decrypt(encrypted_sign_key)
        sign_key_data = json.JSONDecoder().decode(sign_key_raw)
        self.sign_key = base64key_decode(sign_key_data['k'])

        self.__save_msl_data()
        self.handshake_performed = True

    def __load_msl_data(self):
        raw_msl_data = self.load_file(
            msl_data_path=self.kodi_helper.msl_data_path,
            filename='msl_data.json')
        msl_data = json.JSONDecoder().decode(raw_msl_data)
        # Check expire date of the token
        raw_token = msl_data['tokens']['mastertoken']['tokendata']
        base_token = base64.standard_b64decode(raw_token)
        master_token = json.JSONDecoder().decode(base_token)
        exp = int(master_token['expiration'])
        valid_until = datetime.utcfromtimestamp(exp)
        present = datetime.now()
        difference = valid_until - present
        difference = difference.total_seconds() / 60 / 60
        # If token expires in less then 10 hours or is expires renew it
        if difference < 10:
            self.__load_rsa_keys()
            self.__perform_key_handshake()
            return

        self.__set_master_token(msl_data['tokens']['mastertoken'])
        enc_key = msl_data['encryption_key']
        self.encryption_key = base64.standard_b64decode(enc_key)
        self.sign_key = base64.standard_b64decode(msl_data['sign_key'])

    def save_msl_data(self):
        self.__save_msl_data()

    def __save_msl_data(self):
        """
        Saves the keys and tokens in json file
        :return:
        """
        data = {
            "encryption_key": base64.standard_b64encode(self.encryption_key),
            'sign_key': base64.standard_b64encode(self.sign_key),
            'tokens': {
                'mastertoken': self.mastertoken
            }
        }
        serialized_data = json.JSONEncoder().encode(data)
        self.save_file(
            msl_data_path=self.kodi_helper.msl_data_path,
            filename='msl_data.json',
            content=serialized_data)

    def __set_master_token(self, master_token):
        self.mastertoken = master_token
        raw_token = master_token['tokendata']
        base_token = base64.standard_b64decode(raw_token)
        decoded_token = json.JSONDecoder().decode(base_token)
        self.sequence_number = decoded_token.get('sequencenumber')

    def __load_rsa_keys(self):
        loaded_key = self.load_file(
            msl_data_path=self.kodi_helper.msl_data_path,
            filename='rsa_key.bin')
        self.rsa_key = RSA.importKey(loaded_key)

    def __save_rsa_keys(self):
        self.kodi_helper.log(msg='Save RSA Keys')
        # Get the DER Base64 of the keys
        encrypted_key = self.rsa_key.exportKey()
        self.save_file(
            msl_data_path=self.kodi_helper.msl_data_path,
            filename='rsa_key.bin',
            content=encrypted_key)

    @staticmethod
    def file_exists(msl_data_path, filename):
        """
        Checks if a given file exists
        :param filename: The filename
        :return: True if so
        """
        return xbmcvfs.exists(path=msl_data_path + filename)

    @staticmethod
    def save_file(msl_data_path, filename, content):
        """
        Saves the given content under given filename
        :param filename: The filename
        :param content: The content of the file
        """

        file_handle = xbmcvfs.File(msl_data_path + filename, 'w', True)
        file_content = file_handle.write(content)
        file_handle.close()

    @staticmethod
    def load_file(msl_data_path, filename):
        """
        Loads the content of a given filename
        :param filename: The file to load
        :return: The content of the file
        """
        file_handle = xbmcvfs.File(msl_data_path + filename)
        file_content = file_handle.read()
        file_handle.close()
        return file_content
