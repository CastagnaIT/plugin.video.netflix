# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Liberty-developer (original implementation module)
    Copyright (C) 2018 Caphm
    Handling of account credentials

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import base64
import json
from datetime import datetime

from resources.lib.common.exceptions import MissingCredentialsError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG
from .fileops import load_file
from .kodi_ops import get_local_string
from .uuid_device import get_crypt_key

__BLOCK_SIZE__ = 32


def encrypt_credential(raw):
    """
    Encodes data
    :param raw: Data to be encoded
    :type raw: str
    :returns:  string -- Encoded data
    """
    # Keep these imports within the method otherwise if the packages are not installed,
    # the addon crashes and the user does not read the warning message
    try:  # The crypto package depends on the library installed (see Wiki)
        from Cryptodome import Random
        from Cryptodome.Cipher import AES
        from Cryptodome.Util import Padding
    except ImportError:
        from Crypto import Random
        from Crypto.Cipher import AES
        from Crypto.Util import Padding
    raw = bytes(Padding.pad(data_to_pad=raw.encode('utf-8'), block_size=__BLOCK_SIZE__))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(get_crypt_key(), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw)).decode('utf-8')


def decrypt_credential(enc):
    """
    Decodes data
    :param enc: Data to be decoded
    :type enc: str
    :returns:  string -- Decoded data
    """
    # Keep these imports within the method otherwise if the packages are not installed,
    # the addon crashes and the user does not read the warning message
    try:  # The crypto package depends on the library installed (see Wiki)
        from Cryptodome.Cipher import AES
        from Cryptodome.Util import Padding
    except ImportError:
        from Crypto.Cipher import AES
        from Crypto.Util import Padding
    enc = base64.b64decode(enc)
    iv = enc[:AES.block_size]
    cipher = AES.new(get_crypt_key(), AES.MODE_CBC, iv)
    decoded = Padding.unpad(
        padded_data=cipher.decrypt(enc[AES.block_size:]),
        block_size=__BLOCK_SIZE__)
    return decoded


def get_credentials():
    """
    Retrieve stored account credentials.
    :return: The stored account credentials or an empty dict if none exist.
    """
    email = G.LOCAL_DB.get_value('account_email')
    password = G.LOCAL_DB.get_value('account_password')
    verify_credentials(email and password)
    try:
        return {
            'email': decrypt_credential(email).decode('utf-8'),
            'password': decrypt_credential(password).decode('utf-8')
        }
    except Exception as exc:  # pylint: disable=broad-except
        raise MissingCredentialsError('Existing credentials could not be decrypted') from exc


def check_credentials():
    """
    Check if account credentials exists and can be decrypted.
    """
    email = G.LOCAL_DB.get_value('account_email')
    password = G.LOCAL_DB.get_value('account_password')
    try:
        verify_credentials(email and password)
        decrypt_credential(email)
        decrypt_credential(password)
        return True
    except Exception:  # pylint: disable=broad-except
        return False


def set_credentials(credentials):
    """
    Encrypt account credentials and save them.
    """
    G.LOCAL_DB.set_value('account_email', encrypt_credential(credentials['email']))
    G.LOCAL_DB.set_value('account_password', encrypt_credential(credentials['password']))


def purge_credentials():
    """Delete the stored credentials"""
    G.LOCAL_DB.set_value('account_email', None)
    G.LOCAL_DB.set_value('account_password', None)


def verify_credentials(credential):
    """Verify credentials for plausibility"""
    if not credential:
        raise MissingCredentialsError()


def run_nf_authentication_key():
    """
    Start operations to do the login with the authentication key file
    :return: data to send to service or None if user cancel operations or something was wrong
    """
    from resources.lib.kodi import ui
    file_path = ui.show_browse_dialog(get_local_string(30400) + ': NFAuthentication.key', 1, extensions='.key')
    if file_path:
        data = ''
        while data == '':
            pin = ui.show_dlg_input_numeric(get_local_string(30345))
            if pin:
                data = _get_authentication_key_data(file_path, pin)
            else:
                data = None
        if data and _verify_authentication_key_data(data):
            return _prepare_authentication_key_data(data)
    return None


def _get_authentication_key_data(file_path, pin):
    """Open the auth key file"""
    from resources.lib.kodi import ui
    # Keep these imports within the method otherwise if the packages are not installed,
    # the addon crashes and the user does not read the warning message
    try:  # The crypto package depends on the library installed (see Wiki)
        from Cryptodome.Cipher import AES
        from Cryptodome.Util import Padding
    except ImportError:
        from Crypto.Cipher import AES
        from Crypto.Util import Padding
    try:
        file_content = load_file(file_path)
        iv = '\x00' * 16
        cipher = AES.new((pin + pin + pin + pin).encode("utf-8"), AES.MODE_CBC, iv.encode("utf-8"))
        decoded = Padding.unpad(padded_data=cipher.decrypt(base64.b64decode(file_content)),
                                block_size=16)
        return json.loads(decoded.decode('utf-8'))
    except ValueError:
        # ValueError should always means wrong decryption due to wrong key
        ui.show_ok_dialog(get_local_string(30342), get_local_string(30106))
        return ''
    except Exception as exc:  # pylint: disable=broad-except
        LOG.warn('Exception raised: {}', exc)
        ui.show_ok_dialog(get_local_string(30342), get_local_string(30343))
    return None


def _verify_authentication_key_data(data):
    """Verify the data structure"""
    from resources.lib.kodi import ui
    fields = ['app_name', 'app_version', 'app_system', 'app_author', 'timestamp', 'data']
    if not all(name in fields for name in data):
        ui.show_ok_dialog(get_local_string(30342), get_local_string(30343))
        return False
    if not data['data'] or 'cookies' not in data['data']:
        ui.show_ok_dialog(get_local_string(30342), get_local_string(30343))
        return False
    # Check timestamp, session data is not immortal and could cause others side effects
    if datetime.fromtimestamp(data['timestamp']) < datetime.now():
        ui.show_ok_dialog(get_local_string(30342), get_local_string(30344))
        return False
    return True


def _prepare_authentication_key_data(data):
    """Check type of app used and prepare data for the service"""
    from resources.lib.utils.cookies import convert_chrome_cookie
    if (data['app_name'] == 'NFAuthenticationKey' and
            data['app_system'] == 'Windows' and
            # data['app_version'] == '1.0.0.0' and
            data['app_author'] == 'CastagnaIT'):
        result_data = {'cookies': []}
        for cookie in data['data']['cookies']:
            if 'netflix' not in cookie['domain']:
                continue
            result_data['cookies'].append(convert_chrome_cookie(cookie))
        return result_data
    if (data['app_name'] == 'NFAuthenticationKey' and
            data['app_system'] == 'Linux' and
            # data['app_version'] == '1.0.0' and
            data['app_author'] == 'CastagnaIT'):
        result_data = {'cookies': []}
        for cookie in data['data']['cookies']:
            if 'netflix' not in cookie['domain']:
                continue
            result_data['cookies'].append(convert_chrome_cookie(cookie))
        return result_data
    if (data['app_name'] == 'NFAuthenticationKey' and
            data['app_system'] == 'MacOS' and
            # data['app_version'] == '1.0.0' and
            data['app_author'] == 'CastagnaIT'):
        result_data = {'cookies': []}
        for cookie in data['data']['cookies']:
            if 'netflix' not in cookie['domain']:
                continue
            result_data['cookies'].append(convert_chrome_cookie(cookie))
        return result_data
    raise Exception('Authentication key file not supported')
