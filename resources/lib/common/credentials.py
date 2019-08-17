# -*- coding: utf-8 -*-
"""Handling of account credentials"""
from __future__ import unicode_literals

from resources.lib.globals import g
from resources.lib.api.exceptions import MissingCredentialsError

from .logging import debug, error

__BLOCK_SIZE__ = 32
__CRYPT_KEY__ = None


def __crypt_key():
    """
    Lazily generate the crypt key and return it
    """
    # pylint: disable=global-statement
    global __CRYPT_KEY__
    if not __CRYPT_KEY__:
        __CRYPT_KEY__ = __uniq_id()
    return __CRYPT_KEY__


def __uniq_id():
    """
    Returns a unique id based on the devices MAC address
    """
    import uuid
    mac = uuid.getnode()
    if (mac >> 40) % 2:
        from platform import node
        mac = node()
    return uuid.uuid5(uuid.NAMESPACE_DNS, str(mac)).bytes


def encrypt_credential(raw):
    """
    Encodes data

    :param data: Data to be encoded
    :type data: str
    :returns:  string -- Encoded data
    """
    # pylint: disable=invalid-name,import-error
    import base64
    from Cryptodome import Random
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Padding
    raw = bytes(Padding.pad(data_to_pad=raw, block_size=__BLOCK_SIZE__))
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(__crypt_key(), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw))


def decrypt_credential(enc, secret=None):
    """
    Decodes data

    :param data: Data to be decoded
    :type data: str
    :returns:  string -- Decoded data
    """
    # pylint: disable=invalid-name,import-error
    import base64
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Padding
    enc = base64.b64decode(enc)
    iv = enc[:AES.block_size]
    cipher = AES.new(secret or __uniq_id(), AES.MODE_CBC, iv)
    decoded = Padding.unpad(
        padded_data=cipher.decrypt(enc[AES.block_size:]),
        block_size=__BLOCK_SIZE__).decode('utf-8')
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
            'email': decrypt_credential(email),
            'password': decrypt_credential(password)
        }
    except Exception:
        import traceback
        error(traceback.format_exc())
        raise MissingCredentialsError(
            'Existing credentials could not be decrypted')


# noinspection PyBroadException
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
    except Exception:
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
