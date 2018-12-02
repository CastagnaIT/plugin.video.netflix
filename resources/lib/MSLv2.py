# pylint: skip-file
# -*- coding: utf-8 -*-
# Author: trummerjo
# Module: MSLHttpRequestHandler
# Created on: 26.01.2017
# License: MIT https://goo.gl/5bMj3H

import re
import sys
import zlib
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
    last_license_url = ''
    last_drm_context = ''
    last_playback_context = ''

    current_message_id = 0
    session = requests.session()
    rndm = random.SystemRandom()
    tokens = []
    base_url = 'https://www.netflix.com/nq/msl_v1/cadmium/'
    endpoints = {
        'manifest': base_url + 'pbo_manifests/%5E1.0.0/router',
        'license': base_url + 'pbo_licenses/%5E1.0.0/router'
    }

    def __init__(self, nx_common):

      """
      The Constructor checks for already existing crypto Keys.
      If they exist it will load the existing keys
      """
      self.nx_common = nx_common

      self.locale_id = []
      locale_id = nx_common.get_setting('locale_id')
      self.locale_id.append(locale_id if locale_id else 'en-US')

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

        ia_addon = xbmcaddon.Addon('inputstream.adaptive')
        hdcp = ia_addon is not None and ia_addon.getSetting('HDCPOVERRIDE') == 'true'

        esn = self.nx_common.get_esn()
        id = int(time.time() * 10000)
        manifest_request_data = {
            'version': 2,
            'url': '/manifest',
            'id': id,
            'esn': esn,
            'languages': self.locale_id,
            'uiVersion': 'shakti-v25d2fa21',
            'clientVersion': '6.0011.474.011',
            'params': {
                'type': 'standard',
                'viewableId': [viewable_id],
                'flavor': 'PRE_FETCH',
                'drmType': 'widevine',
                'drmVersion': 25,
                'usePsshBox': True,
                'isBranching': False,
                'useHttpsStreams': False,
                'imageSubtitleHeight': 1080,
                'uiVersion': 'shakti-vb45817f4',
                'clientVersion': '6.0011.511.011',
                'supportsPreReleasePin': True,
                'supportsWatermark': True,
                'showAllSubDubTracks': False,
                'titleSpecificData': {},
                'videoOutputInfo': [{
                    'type': 'DigitalVideoOutputDescriptor',
                    'outputType': 'unknown',
                    'supportedHdcpVersions': [],
                    'isHdcpEngaged': hdcp
                }],
                'preferAssistiveAudio': False,
                'isNonMember': False
            }
        }
        manifest_request_data['params']['titleSpecificData'][viewable_id] = { 'unletterboxed': False }

        profiles = ['playready-h264mpl30-dash', 'playready-h264mpl31-dash', 'playready-h264mpl40-dash', 'playready-h264hpl30-dash', 'playready-h264hpl31-dash', 'playready-h264hpl40-dash', 'heaac-2-dash', 'BIF240', 'BIF320']

        # subtitles
        if ia_addon and self.nx_common.compare_versions(map(int, ia_addon.getAddonInfo('version').split('.')), [2, 3, 8]) >= 0:
            profiles.append('webvtt-lssdh-ios8')
        else:
            profiles.append('simplesdh')

        # add hevc profiles if setting is set
        if hevc is True:
            main = 'hevc-main-'
            main10 = 'hevc-main10-'
            prk = 'dash-cenc-prk'
            cenc = 'dash-cenc'
            ctl = 'dash-cenc-tl'
            profiles.append(main10 + 'L41-' + cenc)
            profiles.append(main10 + 'L50-' + cenc)
            profiles.append(main10 + 'L51-' + cenc)
            profiles.append(main + 'L30-' + cenc)
            profiles.append(main + 'L31-' + cenc)
            profiles.append(main + 'L40-' + cenc)
            profiles.append(main + 'L41-' + cenc)
            profiles.append(main + 'L50-' + cenc)
            profiles.append(main + 'L51-' + cenc)
            profiles.append(main10 + 'L30-' + cenc)
            profiles.append(main10 + 'L31-' + cenc)
            profiles.append(main10 + 'L40-' + cenc)
            profiles.append(main10 + 'L41-' + cenc)
            profiles.append(main10 + 'L50-' + cenc)
            profiles.append(main10 + 'L51-' + cenc)
            profiles.append(main10 + 'L30-' + prk)
            profiles.append(main10 + 'L31-' + prk)
            profiles.append(main10 + 'L40-' + prk)
            profiles.append(main10 + 'L41-' + prk)
            profiles.append(main + 'L30-L31-' + ctl)
            profiles.append(main + 'L31-L40-' + ctl)
            profiles.append(main + 'L40-L41-' + ctl)
            profiles.append(main + 'L50-L51-' + ctl)
            profiles.append(main10 + 'L30-L31-' + ctl)
            profiles.append(main10 + 'L31-L40-' + ctl)
            profiles.append(main10 + 'L40-L41-' + ctl)
            profiles.append(main10 + 'L50-L51-' + ctl)

            if hdr is True:
                hdr = 'hevc-hdr-main10-'
                profiles.append(hdr + 'L30-' + cenc)
                profiles.append(hdr + 'L31-' + cenc)
                profiles.append(hdr + 'L40-' + cenc)
                profiles.append(hdr + 'L41-' + cenc)
                profiles.append(hdr + 'L50-' + cenc)
                profiles.append(hdr + 'L51-' + cenc)
                profiles.append(hdr + 'L30-' + prk)
                profiles.append(hdr + 'L31-' + prk)
                profiles.append(hdr + 'L40-' + prk)
                profiles.append(hdr + 'L41-' + prk)
                profiles.append(hdr + 'L50-' + prk)
                profiles.append(hdr + 'L51-' + prk)


            if dolbyvision is True:
                dv = 'hevc-dv-main10-'
                dv5 = 'hevc-dv5-main10-'
                profiles.append(dv + 'L30-' + cenc)
                profiles.append(dv + 'L31-' + cenc)
                profiles.append(dv + 'L40-' + cenc)
                profiles.append(dv + 'L41-' + cenc)
                profiles.append(dv + 'L50-' + cenc)
                profiles.append(dv + 'L51-' + cenc)
                profiles.append(dv5 + 'L30-' + prk)
                profiles.append(dv5 + 'L31-' + prk)
                profiles.append(dv5 + 'L40-' + prk)
                profiles.append(dv5 + 'L41-' + prk)
                profiles.append(dv5 + 'L50-' + prk)
                profiles.append(dv5 + 'L51-' + prk)

        if vp9 is True:
            profiles.append('vp9-profile0-L30-dash-cenc')
            profiles.append('vp9-profile0-L31-dash-cenc')
            profiles.append('vp9-profile0-L32-dash-cenc')
            profiles.append('vp9-profile0-L40-dash-cenc')
            profiles.append('vp9-profile0-L41-dash-cenc')
            profiles.append('vp9-profile0-L50-dash-cenc')
            profiles.append('vp9-profile0-L51-dash-cenc')
            profiles.append('vp9-profile0-L52-dash-cenc')
            profiles.append('vp9-profile0-L60-dash-cenc')
            profiles.append('vp9-profile0-L61-dash-cenc')
            profiles.append('vp9-profile0-L62-dash-cenc')

        # Check if dolby sound is enabled and add to profles
        if dolby:
            profiles.append('ddplus-2.0-dash')
            profiles.append('ddplus-5.1-dash')

        manifest_request_data["params"]["profiles"] = profiles
        #print manifest_request_data

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
        esn = self.nx_common.get_esn()
        id = int(time.time() * 10000)
        license_request_data = {
            'version': 2,
            'url': self.last_license_url,
            'id': id,
            'esn': esn,
            'languages': self.locale_id,
            'uiVersion': 'shakti-v25d2fa21',
            'clientVersion': '6.0011.511.011',
            'params': [{
                'sessionId': sid,
                'clientTime': int(id / 10000),
                'challengeBase64': challenge,
                'xid': str(id + 1610)
            }],
            'echo': 'sessionId'
        }
        #print license_request_data

        request_data = self.__generate_msl_request_data(license_request_data)

        try:
            resp = self.session.post(self.endpoints['license'], request_data)
        except:
            resp = None
            exc = sys.exc_info()
            self.nx_common.log(
                msg='[MSL][POST] Error {} {}'.format(exc[0], exc[1]))

        print resp

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
                if 'licenseResponseBase64' in data[0]:
                    return data[0]['licenseResponseBase64']
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

        decrypted_payload = json.JSONDecoder().decode(decrypted_payload)

        if 'result' in decrypted_payload:
            return decrypted_payload['result']

        decrypted_payload = decrypted_payload[1]['payload']
        if 'json' in decrypted_payload:
            return decrypted_payload['json']['result']
        else:
            decrypted_payload = base64.standard_b64decode(decrypted_payload['data'])
            return json.JSONDecoder().decode(decrypted_payload)


    def __tranform_to_dash(self, manifest):

        self.nx_common.save_file(
            data_path=self.nx_common.data_path,
            filename='manifest.json',
            content=json.dumps(manifest))

        self.last_license_url = manifest['links']['license']['href']
        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']

        seconds = manifest['duration'] / 1000
        init_length = seconds / 2 * 12 + 20 * 1000
        duration = "PT" + str(seconds) + ".00S"

        root = ET.Element('MPD')
        root.attrib['xmlns'] = 'urn:mpeg:dash:schema:mpd:2011'
        root.attrib['xmlns:cenc'] = 'urn:mpeg:cenc:2013'
        root.attrib['mediaPresentationDuration'] = duration

        period = ET.SubElement(root, 'Period', start='PT0S', duration=duration)

        # One Adaption Set for Video
        for video_track in manifest['video_tracks']:
            video_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                mimeType='video/mp4',
                contentType="video")

            # Content Protection
            keyid = None
            pssh = None
            if 'drmHeader' in video_track:
                keyid = video_track['drmHeader']['keyId']
                pssh = video_track['drmHeader']['bytes']

            if keyid:
                protection = ET.SubElement(
                    parent=video_adaption_set,
                    tag='ContentProtection',
                    value='cenc',
                    schemeIdUri='urn:mpeg:dash:mp4protection:2011')
                protection.set('cenc:default_KID', str(uuid.UUID(bytes=base64.standard_b64decode(keyid))))

            protection = ET.SubElement(
                parent=video_adaption_set,
                tag='ContentProtection',
                schemeIdUri='urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED')

            ET.SubElement(
                parent=protection,
                tag='widevine:license',
                robustness_level='HW_SECURE_CODECS_REQUIRED')

            if pssh:
                ET.SubElement(protection, 'cenc:pssh').text = pssh

            for stream in video_track['streams']:

                codec = 'h264'
                if 'hevc' in stream['content_profile']:
                    codec = 'hevc'
                elif 'vp9' in stream['content_profile']:
                    lp = re.search('vp9-profile(.+?)-L(.+?)-dash', stream['content_profile'])
                    codec = 'vp9.' + lp.group(1) + '.' + lp.group(2)

                hdcp_versions = '0.0'
                #for hdcp in stream['hdcpVersions']:
                #    if hdcp != 'none':
                #        hdcp_versions = hdcp if hdcp != 'any' else '1.0'

                rep = ET.SubElement(
                    parent=video_adaption_set,
                    tag='Representation',
                    width=str(stream['res_w']),
                    height=str(stream['res_h']),
                    bandwidth=str(stream['bitrate']*1024),
                    frameRate='%d/%d' % (stream['framerate_value'], stream['framerate_scale']),
                    hdcp=hdcp_versions,
                    nflxContentProfile=str(stream['content_profile']),
                    codecs=codec,
                    mimeType='video/mp4')

                # BaseURL
                base_url = self.__get_base_url(stream['urls'])
                ET.SubElement(rep, 'BaseURL').text = base_url
                # Init an Segment block
                if 'startByteOffset' in stream:
                    initSize = stream['startByteOffset']
                else:
                    sidx = stream['sidx']
                    initSize = sidx['offset'] + sidx['size']

                segment_base = ET.SubElement(
                    parent=rep,
                    tag='SegmentBase',
                    indexRange='0-' + str(initSize),
                    indexRangeExact='true')

        # Multiple Adaption Set for audio
        languageMap = {}
        channelCount = {'1.0':'1', '2.0':'2', '5.1':'6', '7.1':'8'}

        for audio_track in manifest['audio_tracks']:
            impaired = 'true' if audio_track['trackType'] == 'ASSISTIVE' else 'false'
            original = 'true' if audio_track['isNative'] else 'false'
            default = 'false' if audio_track['language'] in languageMap else 'true'
            languageMap[audio_track['language']] = True

            audio_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                lang=audio_track['language'],
                contentType='audio',
                mimeType='audio/mp4',
                impaired=impaired,
                original=original,
                default=default)
            for stream in audio_track['streams']:
                codec = 'aac'
                #self.nx_common.log(msg=stream)
                is_dplus2 = stream['content_profile'] == 'ddplus-2.0-dash'
                is_dplus5 = stream['content_profile'] == 'ddplus-5.1-dash'
                if is_dplus2 or is_dplus5:
                    codec = 'ec-3'
                #self.nx_common.log(msg='codec is: ' + codec)
                rep = ET.SubElement(
                    parent=audio_adaption_set,
                    tag='Representation',
                    codecs=codec,
                    bandwidth=str(stream['bitrate']*1024),
                    mimeType='audio/mp4')

                # AudioChannel Config
                ET.SubElement(
                    parent=rep,
                    tag='AudioChannelConfiguration',
                    schemeIdUri='urn:mpeg:dash:23003:3:audio_channel_configuration:2011',
                    value=channelCount[stream['channels']])

                # BaseURL
                base_url = self.__get_base_url(stream['urls'])
                ET.SubElement(rep, 'BaseURL').text = base_url
                # Index range
                segment_base = ET.SubElement(
                    parent=rep,
                    tag='SegmentBase',
                    indexRange='0-' + str(init_length),
                    indexRangeExact='true')


        # Multiple Adaption Sets for subtiles
        for text_track in manifest.get('timedtexttracks'):
            if text_track['isNoneTrack']:
                continue
            # Only one subtitle representation per adaptationset
            downloadable = text_track['ttDownloadables']
            content_profile = downloadable.keys()[0]

            subtiles_adaption_set = ET.SubElement(
                parent=period,
                tag='AdaptationSet',
                lang=text_track.get('language'),
                codecs='wvtt' if content_profile == 'webvtt-lssdh-ios8' else 'stpp',
                contentType='text',
                mimeType='text/vtt' if content_profile == 'webvtt-lssdh-ios8' else 'application/ttml+xml')
            role = ET.SubElement(
                parent=subtiles_adaption_set,
                tag = 'Role',
                schemeIdUri = 'urn:mpeg:dash:role:2011',
                value = 'forced' if text_track.get('isForcedNarrative') else 'main')
            rep = ET.SubElement(
                parent=subtiles_adaption_set,
                tag='Representation',
                nflxProfile=content_profile)

            base_url = downloadable[content_profile]['downloadUrls'].values()[0]
            ET.SubElement(rep, 'BaseURL').text = base_url

        xml = ET.tostring(root, encoding='utf-8', method='xml')
        xml = xml.replace('\n', '').replace('\r', '')

        self.nx_common.save_file(
            data_path=self.nx_common.data_path,
            filename='manifest.mpd',
            content=xml)

        return xml

    def __get_base_url(self, urls):
        for url in urls:
            return url['url']

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

        # Create FIRST Payload Chunks
        first_payload = {
            'messageid': self.current_message_id,
            'data': base64.standard_b64encode(json.dumps(data)),
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
                'languages': self.locale_id,
                'compressionalgos': compression_algos
            },
            'recipient': 'Netflix',
            'renewable': True,
            'messageid': self.current_message_id,
            'timestamp': time.time()
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
