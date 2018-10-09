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
import uuid
from StringIO import StringIO
from datetime import datetime
import requests
import xml.etree.ElementTree as ET

import xbmcaddon

#check if we are on Android
import subprocess
try:
    sdkversion = int(subprocess.check_output(
        ['/system/bin/getprop', 'ro.build.version.sdk']))
except:
    sdkversion = 0 

if sdkversion >= 18:
  from MSLMediaDrm import MSLMediaDrmCrypto as MSLHandler
else:
  from MSLCrypto import MSLCrypto as MSLHandler

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

    def __init__(self, nx_common):

      """
      The Constructor checks for already existing crypto Keys.
      If they exist it will load the existing keys
      """
      self.nx_common = nx_common

      self.crypto = MSLHandler(nx_common)

      if self.nx_common.file_exists(self.nx_common.data_path, 'msl_data.json'):
          self.init_msl_data()
      else:
          self.crypto.fromDict(None)
          self.__perform_key_handshake()

    def load_manifest(self, viewable_id, dolby, hevc, hdr, dolbyvision, vp9):
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
                'playready-h264bpl30-dash',
                'playready-h264mpl30-dash',
                'playready-h264mpl31-dash',
                'playready-h264mpl40-dash',

                # Audio
                'heaac-2-dash',

                # Subtiltes (handled separately)
                # 'dfxp-ls-sdh',
                # 'simplesdh',
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

        # subtitles
        addon = xbmcaddon.Addon('inputstream.adaptive')
        if addon and self.nx_common.compare_versions(map(int, addon.getAddonInfo('version').split('.')), [2, 3, 8]):
            manifest_request_data['profiles'].append('webvtt-lssdh-ios8')
        else:
            manifest_request_data['profiles'].append('simplesdh')

        # add hevc profiles if setting is set
        if hevc is True:
            main = 'hevc-main-'
            main10 = 'hevc-main10-'
            prk = 'dash-cenc-prk'
            cenc = 'dash-cenc'
            ctl = 'dash-cenc-ctl'
            manifest_request_data['profiles'].append(main10 + 'L41-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L50-' + cenc)
            manifest_request_data['profiles'].append(main10 + 'L51-' + cenc)
            manifest_request_data['profiles'].append(main + 'L30-' + cenc)
            manifest_request_data['profiles'].append(main + 'L31-' + cenc)
            manifest_request_data['profiles'].append(main + 'L40-' + cenc)
            manifest_request_data['profiles'].append(main + 'L41-' + cenc)
            manifest_request_data['profiles'].append(main + 'L50-' + cenc)
            manifest_request_data['profiles'].append(main + 'L51-' + cenc)
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
            manifest_request_data['profiles'].append(main + 'L30-L31-' + ctl)
            manifest_request_data['profiles'].append(main + 'L31-L40-' + ctl)
            manifest_request_data['profiles'].append(main + 'L40-L41-' + ctl)
            manifest_request_data['profiles'].append(main + 'L50-L51-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L30-L31-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L31-L40-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L40-L41-' + ctl)
            manifest_request_data['profiles'].append(main10 + 'L50-L51-' + ctl)

            if hdr is True:
                hdr = 'hevc-hdr-main10-'
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


            if dolbyvision is True:
                dv = 'hevc-dv-main10-'
                dv5 = 'hevc-dv5-main10-'
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

        if hevc is False or vp9 is True:
                manifest_request_data['profiles'].append('vp9-profile0-L30-dash-cenc')
                manifest_request_data['profiles'].append('vp9-profile0-L31-dash-cenc')

        # Check if dolby sound is enabled and add to profles
        if dolby:
            manifest_request_data['profiles'].append('ddplus-2.0-dash')
            manifest_request_data['profiles'].append('ddplus-5.1-dash')

        request_data = self.__generate_msl_request_data(manifest_request_data)

        try:
            resp = self.session.post(self.endpoints['manifest'], request_data)
        except:
            resp = None
            exc = sys.exc_info()
            msg = '[MSL][POST] Error {} {}'
            self.nx_common.log(msg=msg.format(exc[0], exc[1]))

        if resp:
            try:
                # if the json() does not fail we have an error because
                # the manifest response is a chuncked json response
                resp.json()
                self.nx_common.log(
                    msg='Error getting Manifest: ' + resp.text)
                return False
            except ValueError:
                # json() failed so parse the chunked response
                #self.nx_common.log(
                #    msg='Got chunked Manifest Response: ' + resp.text)
                resp = self.__parse_chunked_msl_response(resp.text)
                #self.nx_common.log(
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
            self.nx_common.log(
                msg='[MSL][POST] Error {} {}'.format(exc[0], exc[1]))

        if resp:
            try:
                # If is valid json the request for the licnese failed
                resp.json()
                self.nx_common.log(msg='Error getting license: '+resp.text)
                return False
            except ValueError:
                # json() failed so we have a chunked json response
                resp = self.__parse_chunked_msl_response(resp.text)
                data = self.__decrypt_payload_chunks(resp['payloads'])
                if data['success'] is True:
                    return data['result']['licenses'][0]['data']
                else:
                    self.nx_common.log(
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

        self.nx_common.save_file(
            data_path=self.nx_common.data_path,
            filename='manifest.json',
            content=json.dumps(manifest))
        manifest = manifest['result']['viewables'][0]

        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']

        # Check for pssh
        pssh = ''
        keyid = None
        if 'psshb64' in manifest:
            if len(manifest['psshb64']) >= 1:
                pssh = manifest['psshb64'][0]
                psshbytes = base64.standard_b64decode(pssh)
                if len(psshbytes) == 52:
                    keyid = psshbytes[36:]

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
            if keyid:
                protection = ET.SubElement(
                    parent=video_adaption_set,
                    tag='ContentProtection',
                    value='cenc',
                    schemeIdUri='urn:mpeg:dash:mp4protection:2011')
                protection.set('cenc:default_KID', str(uuid.UUID(bytes=keyid)))

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
                elif downloadable['contentProfile'] == 'vp9-profile0-L30-dash-cenc':
                  codec = 'vp9.0.30'
                elif downloadable['contentProfile'] == 'vp9-profile0-L31-dash-cenc':
                  codec = 'vp9.0.31'

                hdcp_versions = '0.0'
                for hdcp in downloadable['hdcpVersions']:
                    if hdcp != 'none':
                        hdcp_versions = hdcp if hdcp != 'any' else '1.0'

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

        # Multiple Adaption Set for audio
        language = None
        for audio_track in manifest['audioTracks']:
            impaired = 'false'
            original = 'false'
            default = 'false'

            if audio_track.get('trackType') == 'ASSISTIVE':
                impaired = 'true'
            elif not language or language == audio_track.get('language'):
                language = audio_track.get('language')
                default = 'true'
            if audio_track.get('language').find('[') > 0:
                original = 'true'

            audio_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                lang=audio_track['bcp47'],
                contentType='audio',
                mimeType='audio/mp4',
                impaired=impaired,
                original=original,
                default=default)
            for downloadable in audio_track['downloadables']:
                codec = 'aac'
                #self.nx_common.log(msg=downloadable)
                is_dplus2 = downloadable['contentProfile'] == 'ddplus-2.0-dash'
                is_dplus5 = downloadable['contentProfile'] == 'ddplus-5.1-dash'
                if is_dplus2 or is_dplus5:
                    codec = 'ec-3'
                #self.nx_common.log(msg='codec is: ' + codec)
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

        # Multiple Adaption Sets for subtiles
        for text_track in manifest.get('textTracks'):
            is_downloadables = 'downloadables' not in text_track
            if is_downloadables or text_track.get('downloadables') is None:
                continue
            # Only one subtitle representation per adaptationset
            downloadable = text_track['downloadables'][0]

            subtiles_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                lang=text_track.get('bcp47'),
                codecs='wvtt' if downloadable.get('contentProfile') == 'webvtt-lssdh-ios8' else 'stpp',
                contentType='text',
                mimeType='text/vtt' if downloadable.get('contentProfile') == 'webvtt-lssdh-ios8' else 'application/ttml+xml')
            role = ET.SubElement(
                parent=subtiles_adaption_set,
                tag = 'Role',
                schemeIdUri = 'urn:mpeg:dash:role:2011',
                value = 'forced' if text_track.get('isForced') == True else 'main')
            rep = ET.SubElement(
                parent=subtiles_adaption_set,
                tag='Representation',
                nflxProfile=downloadable.get('contentProfile'))
            base_url = self.__get_base_url(downloadable['urls'])
            ET.SubElement(rep, 'BaseURL').text = base_url

        xml = ET.tostring(root, encoding='utf-8', method='xml')
        xml = xml.replace('\n', '').replace('\r', '')

        self.nx_common.save_file(
            data_path=self.nx_common.data_path,
            filename='manifest.mpd',
            content=xml)

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
        #self.__load_msl_data()
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
        esn = self.nx_common.get_esn()

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
                account = self.nx_common.get_credentials()
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
        return json.dumps(self.crypto.encrypt(plaintext, self.nx_common.get_esn(), self.sequence_number))

    def __sign(self, text):
        """
        Calculates the HMAC signature for the given
        text with the current sign key and SHA256

        :param text:
        :return: Base64 encoded signature
        """
        return base64.standard_b64encode(self.crypto.sign(text))

    def perform_key_handshake(self):
        self.__perform_key_handshake()

    def __perform_key_handshake(self):
        esn = self.nx_common.get_esn()
        self.nx_common.log(msg='perform_key_handshake: esn:' + esn)

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
        #self.nx_common.log(msg='Key Handshake Request:')
        #self.nx_common.log(msg=json.dumps(request))

        try:
            resp = self.session.post(
                url=self.endpoints['manifest'],
                data=json.dumps(request, sort_keys=True))
        except:
            resp = None
            exc = sys.exc_info()
            self.nx_common.log(
                msg='[MSL][POST] Error {} {}'.format(exc[0], exc[1]))

        if resp and resp.status_code == 200:
            resp = resp.json()
            if 'errordata' in resp:
                self.nx_common.log(msg='Key Exchange failed')
                self.nx_common.log(
                    msg=base64.standard_b64decode(resp['errordata']))
                return False
            base_head = base64.standard_b64decode(resp['headerdata'])

            headerdata=json.JSONDecoder().decode(base_head)
            self.__set_master_token(headerdata['keyresponsedata']['mastertoken'])
            self.crypto.parse_key_response(headerdata)
            self.__save_msl_data()
        else:
            self.nx_common.log(msg='Key Exchange failed')
            self.nx_common.log(msg=resp.text)

    def init_msl_data(self):
        self.nx_common.log(msg='MSL Data exists. Use old Tokens.')
        self.__load_msl_data()
        self.handshake_performed = True

    def __load_msl_data(self):
        raw_msl_data = self.nx_common.load_file(
            data_path=self.nx_common.data_path,
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
        # If token expires in less then 10 hours or is expires renew it
        self.nx_common.log(msg='Expiration time: Key:' + str(valid_until) + ', Now:' + str(present) + ', Diff:' + str(difference.total_seconds()))
        difference = difference.total_seconds() / 60 / 60
        if self.crypto.fromDict(msl_data) or difference < 10:
            self.__perform_key_handshake()
            return

        self.__set_master_token(msl_data['tokens']['mastertoken'])

    def save_msl_data(self):
        self.__save_msl_data()

    def __save_msl_data(self):
        """
        Saves the keys and tokens in json file
        :return:
        """
        data = {
            'tokens': {
                'mastertoken': self.mastertoken
            }
        }
        data.update(self.crypto.toDict())

        serialized_data = json.JSONEncoder().encode(data)
        self.nx_common.save_file(
            data_path=self.nx_common.data_path,
            filename='msl_data.json',
            content=serialized_data)

    def __set_master_token(self, master_token):
        self.mastertoken = master_token
        raw_token = master_token['tokendata']
        base_token = base64.standard_b64decode(raw_token)
        decoded_token = json.JSONDecoder().decode(base_token)
        self.sequence_number = decoded_token.get('sequencenumber')
