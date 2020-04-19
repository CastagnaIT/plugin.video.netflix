# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>
    This file implements the Kodi xbmcvfs module, either using stubs or alternative functionality

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
# pylint: disable=unused-argument

from __future__ import absolute_import, division, print_function, unicode_literals


class CryptoSession:
    """A reimplementation of the xbmcdrm CryptoSession class"""

    def __init__(self, UUID, cipherAlgorithm, macAlgorithm):
        """A stub constructor for the xbmcdrm CryptoSession class"""

    def Decrypt(self, cipherKeyId, input, iv):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcdrm CryptoSession class Decrypt() method"""
        return ''

    def Encrypt(self, cipherKeyId, input, iv):  # pylint: disable=redefined-builtin
        """A stub implementation for the xbmcdrm CryptoSession class Encrypt() method"""
        return ''

    def GetKeyRequest(self, init, mimeType, offlineKey, optionalParameters):
        """A stub implementation for the xbmcdrm CryptoSession class GetKeyRequest() method"""
        return

    def GetPropertyString(self, name):
        """A stub implementation for the xbmcdrm CryptoSession class GetPropertyString() method"""
        return

    def ProvideKeyResponse(self, response):
        """A stub implementation for the xbmcdrm CryptoSession class ProvideKeyResponse() method"""
        return

    def RemoveKeys(self):
        """A stub implementation for the xbmcdrm CryptoSession class RemoveKeys() method"""

    def RestoreKeys(self, keySetId):
        """A stub implementation for the xbmcdrm CryptoSession class RestoreKeys() method"""

    def SetPropertyString(self, name, value):
        """A stub implementation for the xbmcdrm CryptoSession class SetPropertyString() method"""
        return value

    def Sign(self, macKeyId, message):
        """A stub implementation for the xbmcdrm CryptoSession class Sign() method"""
        return b''

    def Verify(self, macKeyId, message, signature):
        """A stub implementation for the xbmcdrm CryptoSession class Verify() method"""
        return True
