import base64
import gzip
import json
import os
import pprint
import random
from StringIO import StringIO
from hmac import HMAC
import hashlib
import requests
import zlib

import time
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
# from Crypto.Hash import HMAC, SHA256
from Crypto.Util import Padding
import xml.etree.ElementTree as ET

pp = pprint.PrettyPrinter(indent=4)

def base64key_decode(payload):
    l = len(payload) % 4
    if l == 2:
        payload += '=='
    elif l == 3:
        payload += '='
    elif l != 0:
        raise ValueError('Invalid base64 string')
    return base64.urlsafe_b64decode(payload.encode('utf-8'))


class MSL:
    handshake_performed = False  # Is a handshake already performed and the keys loaded
    last_drm_context = ''
    last_playback_context = ''
    #esn = "NFCDCH-LX-CQE0NU6PA5714R25VPLXVU2A193T36"
    esn = "WWW-BROWSE-D7GW1G4NPXGR1F0X1H3EQGY3V1F5WE"
    current_message_id = 0
    session = requests.session()
    rndm = random.SystemRandom()
    tokens = []
    endpoints = {
        'manifest': 'http://www.netflix.com/api/msl/NFCDCH-LX/cadmium/manifest',
        'license': 'http://www.netflix.com/api/msl/NFCDCH-LX/cadmium/license'
    }

    def __init__(self, email, password, kodi_helper):
        """
        The Constructor checks for already existing crypto Keys.
        If they exist it will load the existing keys
        """
        self.email = email
        self.password = password
        self.kodi_helper = kodi_helper
        try:
            os.mkdir(self.kodi_helper.msl_data_path)
        except OSError:
            pass

        if self.file_exists(self.kodi_helper.msl_data_path, 'msl_data.json'):
            self.__load_msl_data()
            self.handshake_performed = True
        elif self.file_exists(self.kodi_helper.msl_data_path, 'rsa_key.bin'):
            self.kodi_helper.log(msg='RSA Keys do already exist load old ones')
            self.__load_rsa_keys()
            self.__perform_key_handshake()
        else:
            self.kodi_helper.log(msg='Create new RSA Keys')
            # Create new Key Pair and save
            self.rsa_key = RSA.generate(2048)
            self.__save_rsa_keys()
            self.__perform_key_handshake()

    def load_manifest(self, viewable_id):
        manifest_request_data = {
            'method': 'manifest',
            'lookupType': 'PREPARE',
            'viewableIds': [viewable_id],
            'profiles': [
                'playready-h264mpl30-dash',
                'playready-h264mpl31-dash',
                'heaac-2-dash',
                'dfxp-ls-sdh',
                'simplesdh',
                'nflx-cmisc',
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
        request_data = self.__generate_msl_request_data(manifest_request_data)

        resp = self.session.post(self.endpoints['manifest'], request_data)


        try:
            resp.json()
            self.kodi_helper.log(msg='MANIFEST RESPONE JSON: '+resp.text)
        except ValueError:
            # Maybe we have a CHUNKED response
            resp = self.__parse_chunked_msl_response(resp.text)
            data = self.__decrypt_payload_chunk(resp['payloads'][0])
            # pprint.pprint(data)
            return self.__tranform_to_dash(data)


    def get_license(self, challenge, sid):

        """
            std::time_t t = std::time(0);  // t is an integer type
    licenseRequestData["clientTime"] = (int)t;
    //licenseRequestData["challengeBase64"] = challengeStr;
    licenseRequestData["licenseType"] = "STANDARD";
    licenseRequestData["playbackContextId"] = playbackContextId;//"E1-BQFRAAELEB32o6Se-GFvjwEIbvDydEtfj6zNzEC3qwfweEPAL3gTHHT2V8rS_u1Mc3mw5BWZrUlKYIu4aArdjN8z_Z8t62E5jRjLMdCKMsVhlSJpiQx0MNW4aGqkYz-1lPh85Quo4I_mxVBG5lgd166B5NDizA8.";
    licenseRequestData["drmContextIds"] = Json::arrayValue;
    licenseRequestData["drmContextIds"].append(drmContextId);

        :param viewable_id:
        :param challenge:
        :param kid:
        :return:
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

        resp = self.session.post(self.endpoints['license'], request_data)

        try:
            resp.json()
            self.kodi_helper.log(msg='LICENSE RESPONE JSON: '+resp.text)
        except ValueError:
            # Maybe we have a CHUNKED response
            resp = self.__parse_chunked_msl_response(resp.text)
            data = self.__decrypt_payload_chunk(resp['payloads'][0])
            # pprint.pprint(data)
            if data['success'] is True:
                return data['result']['licenses'][0]['data']
            else:
                return ''


    def __decrypt_payload_chunk(self, payloadchunk):
        payloadchunk = json.JSONDecoder().decode(payloadchunk)
        encryption_envelope = json.JSONDecoder().decode(base64.standard_b64decode(payloadchunk['payload']))
        # Decrypt the text
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, base64.standard_b64decode(encryption_envelope['iv']))
        plaintext = cipher.decrypt(base64.standard_b64decode(encryption_envelope['ciphertext']))
        # unpad the plaintext
        plaintext = json.JSONDecoder().decode(Padding.unpad(plaintext, 16))
        data = plaintext['data']

        # uncompress data if compressed
        if plaintext['compressionalgo'] == 'GZIP':
            data = zlib.decompress(base64.standard_b64decode(data), 16 + zlib.MAX_WBITS)
        else:
            data = base64.standard_b64decode(data)

        data = json.JSONDecoder().decode(data)[1]['payload']['data']
        data = base64.standard_b64decode(data)
        return json.JSONDecoder().decode(data)


    def __tranform_to_dash(self, manifest):

        self.save_file(self.kodi_helper.msl_data_path, 'manifest.json', json.dumps(manifest))
        manifest = manifest['result']['viewables'][0]

        self.last_playback_context = manifest['playbackContextId']
        self.last_drm_context = manifest['drmContextId']

        #Check for pssh
        pssh = ''
        if 'psshb64' in manifest:
            if len(manifest['psshb64']) >= 1:
                pssh = manifest['psshb64'][0]



        root = ET.Element('MPD')
        root.attrib['xmlns'] = 'urn:mpeg:dash:schema:mpd:2011'
        root.attrib['xmlns:cenc'] = 'urn:mpeg:cenc:2013'


        seconds = manifest['runtime']/1000
        duration = "PT"+str(seconds)+".00S"

        period = ET.SubElement(root, 'Period', start='PT0S', duration=duration)

        # One Adaption Set for Video
        for video_track in manifest['videoTracks']:
            video_adaption_set = ET.SubElement(period, 'AdaptationSet', mimeType='video/mp4', contentType="video")
            # Content Protection
            protection = ET.SubElement(video_adaption_set, 'ContentProtection',
                          schemeIdUri='urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED')
            if pssh is not '':
                ET.SubElement(protection, 'cenc:pssh').text = pssh

            for downloadable in video_track['downloadables']:
                rep = ET.SubElement(video_adaption_set, 'Representation',
                                    width=str(downloadable['width']),
                                    height=str(downloadable['height']),
                                    bandwidth=str(downloadable['bitrate']*1024),
                                    codecs='h264',
                                    mimeType='video/mp4')

                #BaseURL
                ET.SubElement(rep, 'BaseURL').text = self.__get_base_url(downloadable['urls'])
                # Init an Segment block
                segment_base = ET.SubElement(rep, 'SegmentBase', indexRange="0-60000", indexRangeExact="true")
                ET.SubElement(segment_base, 'Initialization', range='0-60000')



        # Multiple Adaption Set for audio
        for audio_track in manifest['audioTracks']:
            audio_adaption_set = ET.SubElement(period, 'AdaptationSet',
                                               lang=audio_track['bcp47'],
                                               contentType='audio',
                                               mimeType='audio/mp4')
            for downloadable in audio_track['downloadables']:
                rep = ET.SubElement(audio_adaption_set, 'Representation',
                                    codecs='aac',
                                    bandwidth=str(downloadable['bitrate']*1024),
                                    mimeType='audio/mp4')

                #AudioChannel Config
                ET.SubElement(rep, 'AudioChannelConfiguration',
                              schemeIdUri='urn:mpeg:dash:23003:3:audio_channel_configuration:2011',
                              value=str(audio_track['channelsCount']))

                #BaseURL
                ET.SubElement(rep, 'BaseURL').text = self.__get_base_url(downloadable['urls'])
                # Index range
                segment_base = ET.SubElement(rep, 'SegmentBase', indexRange="0-60000", indexRangeExact="true")
                ET.SubElement(segment_base, 'Initialization', range='0-60000')


        xml = ET.tostring(root, encoding='utf-8', method='xml')
        xml = xml.replace('\n', '').replace('\r', '')
        return xml

    def __get_base_url(self, urls):
        for key in urls:
            return urls[key]

    def __parse_chunked_msl_response(self, message):
        i = 0
        opencount = 0
        closecount = 0
        header = ""
        payloads = []
        old_end = 0

        while i < len(message):
            if message[i] == '{':
                opencount = opencount + 1
            if message[i] == '}':
                closecount = closecount + 1
            if opencount == closecount:
                if header == "":
                    header = message[:i]
                    old_end = i + 1
                else:
                    payloads.append(message[old_end:i + 1])
            i += 1

        return {
            'header': header,
            'payloads': payloads
        }

    def __generate_msl_request_data(self, data):
        header_encryption_envelope = self.__encrypt(self.__generate_msl_header())
        header = {
            'headerdata': base64.standard_b64encode(header_encryption_envelope),
            'signature': self.__sign(header_encryption_envelope),
            'mastertoken': self.mastertoken,
        }

        # Serialize the given Data
        serialized_data = json.dumps(data)
        serialized_data = serialized_data.replace('"', '\\"')
        serialized_data = '[{},{"headers":{},"path":"/cbp/cadmium-11","payload":{"data":"' + serialized_data + '"},"query":""}]\n'

        compressed_data = self.__compress_data(serialized_data)

        # Create FIRST Payload Chunks
        first_payload = {
            "messageid": self.current_message_id,
            "data": compressed_data,
            "compressionalgo": "GZIP",
            "sequencenumber": 1,
            "endofmsg": True
        }
        first_payload_encryption_envelope = self.__encrypt(json.dumps(first_payload))
        first_payload_chunk = {
            'payload': base64.standard_b64encode(first_payload_encryption_envelope),
            'signature': self.__sign(first_payload_encryption_envelope),
        }


        # Create Second Payload
        second_payload = {
            "messageid": self.current_message_id,
            "data": "",
            "endofmsg": True,
            "sequencenumber": 2
        }
        second_payload_encryption_envelope = self.__encrypt(json.dumps(second_payload))
        second_payload_chunk = {
            'payload': base64.standard_b64encode(second_payload_encryption_envelope),
            'signature': base64.standard_b64encode(self.__sign(second_payload_encryption_envelope)),
        }

        request_data = json.dumps(header) + json.dumps(first_payload_chunk) # + json.dumps(second_payload_chunk)
        return request_data



    def __compress_data(self, data):
        # GZIP THE DATA
        out = StringIO()
        with gzip.GzipFile(fileobj=out, mode="w") as f:
            f.write(data)
        return base64.standard_b64encode(out.getvalue())


    def __generate_msl_header(self, is_handshake=False, is_key_request=False, compressionalgo="GZIP", encrypt=True):
        """
        Function that generates a MSL header dict
        :return: The base64 encoded JSON String of the header
        """
        self.current_message_id = self.rndm.randint(0, pow(2, 52))

        header_data = {
            'sender': self.esn,
            'handshake': is_handshake,
            'nonreplayable': False,
            'capabilities': {
                'languages': ["en-US"],
                'compressionalgos': []
            },
            'recipient': 'Netflix',
            'renewable': True,
            'messageid': self.current_message_id,
            'timestamp': 1467733923
        }

        # Add compression algo if not empty
        if compressionalgo is not "":
            header_data['capabilities']['compressionalgos'].append(compressionalgo)

        # If this is a keyrequest act diffrent then other requests
        if is_key_request:
            public_key = base64.standard_b64encode(self.rsa_key.publickey().exportKey(format='DER'))
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
                # Auth via email and password
                header_data['userauthdata'] = {
                    'scheme': 'EMAIL_PASSWORD',
                    'authdata': {
                        'email': self.email,
                        'password': self.password
                    }
                }

        return json.dumps(header_data)



    def __encrypt(self, plaintext):
        """
        Encrypt the given Plaintext with the encryption key
        :param plaintext:
        :return: Serialized JSON String of the encryption Envelope
        """
        iv = get_random_bytes(16)
        encryption_envelope = {
            'ciphertext': '',
            'keyid': self.esn + '_' + str(self.sequence_number),
            'sha256': 'AA==',
            'iv': base64.standard_b64encode(iv)
        }
        # Padd the plaintext
        plaintext = Padding.pad(plaintext, 16)
        # Encrypt the text
        cipher = AES.new(self.encryption_key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(plaintext)
        encryption_envelope['ciphertext'] = base64.standard_b64encode(ciphertext)
        return json.dumps(encryption_envelope)

    def __sign(self, text):
        #signature = hmac.new(self.sign_key, text, hashlib.sha256).digest()
        signature = HMAC(self.sign_key, text, hashlib.sha256).digest()


        # hmac = HMAC.new(self.sign_key, digestmod=SHA256)
        # hmac.update(text)
        return base64.standard_b64encode(signature)


    def __perform_key_handshake(self):

        header = self.__generate_msl_header(is_key_request=True, is_handshake=True, compressionalgo="", encrypt=False)
        request = {
            'entityauthdata': {
                'scheme': 'NONE',
                'authdata': {
                    'identity': self.esn
                }
            },
            'headerdata': base64.standard_b64encode(header),
            'signature': '',
        }
        self.kodi_helper.log(msg='Key Handshake Request:')
        self.kodi_helper.log(msg=json.dumps(request))


        resp = self.session.post(self.endpoints['manifest'], json.dumps(request, sort_keys=True))
        if resp.status_code == 200:
            resp = resp.json()
            if 'errordata' in resp:
                self.kodi_helper.log(msg='Key Exchange failed')
                self.kodi_helper.log(msg=base64.standard_b64decode(resp['errordata']))
                return False
            self.__parse_crypto_keys(json.JSONDecoder().decode(base64.standard_b64decode(resp['headerdata'])))
        else:
            self.kodi_helper.log(msg='Key Exchange failed')
            self.kodi_helper.log(msg=resp.text)

    def __parse_crypto_keys(self, headerdata):
        self.__set_master_token(headerdata['keyresponsedata']['mastertoken'])
        # Init Decryption
        encrypted_encryption_key = base64.standard_b64decode(headerdata['keyresponsedata']['keydata']['encryptionkey'])
        encrypted_sign_key = base64.standard_b64decode(headerdata['keyresponsedata']['keydata']['hmackey'])
        cipher_rsa = PKCS1_OAEP.new(self.rsa_key)

        # Decrypt encryption key
        encryption_key_data = json.JSONDecoder().decode(cipher_rsa.decrypt(encrypted_encryption_key))
        self.encryption_key = base64key_decode(encryption_key_data['k'])

        # Decrypt sign key
        sign_key_data = json.JSONDecoder().decode(cipher_rsa.decrypt(encrypted_sign_key))
        self.sign_key = base64key_decode(sign_key_data['k'])

        self.__save_msl_data()
        self.handshake_performed = True

    def __load_msl_data(self):
        msl_data = json.JSONDecoder().decode(self.load_file(self.kodi_helper.msl_data_path, 'msl_data.json'))
        self.__set_master_token(msl_data['tokens']['mastertoken'])
        self.encryption_key = base64.standard_b64decode(msl_data['encryption_key'])
        self.sign_key = base64.standard_b64decode(msl_data['sign_key'])

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
        self.save_file(self.kodi_helper.msl_data_path, 'msl_data.json', serialized_data)

    def __set_master_token(self, master_token):
        self.mastertoken = master_token
        self.sequence_number = json.JSONDecoder().decode(base64.standard_b64decode(master_token['tokendata']))[
            'sequencenumber']

    def __load_rsa_keys(self):
        loaded_key = self.load_file(self.kodi_helper.msl_data_path, 'rsa_key.bin')
        self.rsa_key = RSA.importKey(loaded_key)

    def __save_rsa_keys(self):
        self.kodi_helper.log(msg='Save RSA Keys')
        # Get the DER Base64 of the keys
        encrypted_key = self.rsa_key.exportKey()
        self.save_file(self.kodi_helper.msl_data_path, 'rsa_key.bin', encrypted_key)

    @staticmethod
    def file_exists(msl_data_path, filename):
        """
        Checks if a given file exists
        :param filename: The filename
        :return: True if so
        """
        return os.path.isfile(msl_data_path + filename)

    @staticmethod
    def save_file(msl_data_path, filename, content):
        """
        Saves the given content under given filename
        :param filename: The filename
        :param content: The content of the file
        """
        with open(msl_data_path + filename, 'w') as file_:
            file_.write(content)
            file_.flush()

    @staticmethod
    def load_file(msl_data_path, filename):
        """
        Loads the content of a given filename
        :param filename: The file to load
        :return: The content of the file
        """
        with open(msl_data_path + filename) as file_:
            file_content = file_.read()
        return file_content
