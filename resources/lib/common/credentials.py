# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Liberty-developer (original implementation module)
    Copyright (C) 2018 Caphm
    Handling of account credentials

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from resources.lib.globals import g
from resources.lib.api.exceptions import MissingCredentialsError

from .logging import error
from .uuid_device import get_crypt_key

__BLOCK_SIZE__ = 32


def encrypt_credential(raw):
    """
    Encodes data

    :param data: Data to be encoded
    :type data: str
    :returns:  string -- Encoded data
    """
    # pylint: disable=invalid-name,import-error
    import base64
    try:  # The crypto package depends on the library installed (see Wiki)
        from Crypto import Random
        from Crypto.Cipher import AES
        from Crypto.Util import Padding
    except ImportError:
        from Cryptodome import Random
        from Cryptodome.Cipher import AES
        from Cryptodome.Util import Padding
    raw = bytes(Padding.pad(data_to_pad=raw.encode('utf-8'), block_size=__BLOCK_SIZE__))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(get_crypt_key(), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw)).decode('utf-8')


def decrypt_credential(enc, secret=None):
    """
    Decodes data

    :param data: Data to be decoded
    :type data: str
    :returns:  string -- Decoded data
    """
    # pylint: disable=invalid-name,import-error
    import base64
    try:  # The crypto package depends on the library installed (see Wiki)
        from Crypto.Cipher import AES
        from Crypto.Util import Padding
    except ImportError:
        from Cryptodome.Cipher import AES
        from Cryptodome.Util import Padding
    enc = base64.b64decode(enc)
    iv = enc[:AES.block_size]
    cipher = AES.new(secret or get_crypt_key(), AES.MODE_CBC, iv)
    decoded = Padding.unpad(
        padded_data=cipher.decrypt(enc[AES.block_size:]),
        block_size=__BLOCK_SIZE__)
    return decoded


def get_credentials():
    """
    Retrieve stored account credentials.
    :return: The stored account credentials or an empty dict if none exist.
    """
    email = g.LOCAL_DB.get_value('account_email')
    password = g.LOCAL_DB.get_value('account_password')
    verify_credentials(email and password)
    try:
        return {
            'email': decrypt_credential(email).decode('utf-8'),
            'password': decrypt_credential(password).decode('utf-8')
        }
    except Exception:
        import traceback
        error(g.py2_decode(traceback.format_exc(), 'latin-1'))
        raise MissingCredentialsError(
            'Existing credentials could not be decrypted')


def check_credentials():
    """
    Check if account credentials exists and can be decrypted.
    """
    email = g.LOCAL_DB.get_value('account_email')
    password = g.LOCAL_DB.get_value('account_password')
    try:
        verify_credentials(email and password)
        decrypt_credential(email)
        decrypt_credential(password)
        return True
    except Exception:  # pylint: disable=broad-except
        pass
    return False


def set_credentials(email, password):
    """
    Encrypt account credentials and save them to the settings.
    Does nothing if either email or password are not supplied.
    """
    if email and password:
        g.LOCAL_DB.set_value('account_email', encrypt_credential(email))
        g.LOCAL_DB.set_value('account_password', encrypt_credential(password))


def purge_credentials():
    """Delete the stored credentials"""
    g.LOCAL_DB.set_value('account_email', None)
    g.LOCAL_DB.set_value('account_password', None)


def verify_credentials(credential):
    """Verify credentials for plausibility"""
    if not credential:
        raise MissingCredentialsError()
