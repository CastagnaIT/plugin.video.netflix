# -*- coding: utf-8 -*-
# Module: KodiHelper
# Author: asciidisco
# Created on: 11.10.2017
# License: MIT https://goo.gl/5bMj3H

"""Tests for the `KodiHelper` module"""

import unittest
import mock
from resources.lib.KodiHelper import KodiHelper

class KodiHelperTestCase(unittest.TestCase):

    @mock.patch('xbmc.getInfoLabel')
    def test_encode(self, mock_getInfoLabel):
        """ADD ME"""
        mock_getInfoLabel.return_value = '00:80:41:ae:fd:7e'
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.decode(kodi_helper.encode('foo')),
            second='foo')

    @mock.patch('xbmc.getInfoLabel')
    def test_decode(self, mock_getInfoLabel):
        """ADD ME"""
        mock_getInfoLabel.return_value = '00:80:41:ae:fd:7e'
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.decode('UElth5ymr6hRVIderI80WpSTteTFDeWB3vr7JK/N9QqAuNvriQGZRznH+KCPyiCS'),
            second='foo')
