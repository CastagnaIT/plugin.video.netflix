# -*- coding: utf-8 -*-
"""Handling of account credentials"""
from __future__ import unicode_literals

from resources.lib.globals import g
from resources.lib.api.exceptions import MissingCredentialsError

from .logging import debug

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
    email = g.ADDON.getSetting('email')
    password = g.ADDON.getSetting('password')
    verify_credentials(email and password)
    try:
        return {
            'email': decrypt_credential(email),
            'password': decrypt_credential(password)
        }
    except ValueError:
        return migrate_credentials(email, password)


def migrate_credentials(encrypted_email, encrypted_password):
    """Try to decrypt stored credentials with the old unsafe secret and update
    them to new safe format"""
    unsafe_secret = 'UnsafeStaticSecret'.encode()
    try:
        email = decrypt_credential(encrypted_email, secret=unsafe_secret)
        password = decrypt_credential(encrypted_password, secret=unsafe_secret)
    except ValueError:
        raise MissingCredentialsError(
            'Existing credentials could not be decrypted')
    set_credentials(email, password)
    debug('Migrated old unsafely stored credentials to new safe format')
    return {'email': email, 'password': password}


def set_credentials(email, password):
    """
    Encrypt account credentials and save them to the settings.
    Does nothing if either email or password are not supplied.
    """
    if email and password:
        g.SETTINGS_MONITOR_IGNORE = True
        g.ADDON.setSetting('email', encrypt_credential(email))
        g.ADDON.setSetting('password', encrypt_credential(password))
        g.SETTINGS_MONITOR_IGNORE = False


def purge_credentials():
    """Delete the stored credentials"""
    g.SETTINGS_MONITOR_IGNORE = True
    g.ADDON.setSetting('email', '')
    g.ADDON.setSetting('password', '')
    g.SETTINGS_MONITOR_IGNORE = False


def verify_credentials(credential):
    """Verify credentials for plausibility"""
    if not credential:
        raise MissingCredentialsError()
