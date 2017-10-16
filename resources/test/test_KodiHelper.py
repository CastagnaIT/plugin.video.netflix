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

    def test_refresh(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.refresh(),
            second=None)

    def test_invalidate_memcache(self):
        """ADD ME"""
        cache = KodiHelper()
        self.assertEqual(
            first=cache.invalidate_memcache(),
            second=None)

    def test_set_main_menu_selection(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.set_main_menu_selection('foo'),
            second=None)
        self.assertEqual(
            first=kodi_helper.get_main_menu_selection(),
            second='')

    def test_get_main_menu_selection(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        kodi_helper.set_main_menu_selection('foo')
        self.assertEqual(
            first=kodi_helper.get_main_menu_selection(),
            second='')

    def test_get_cached_item(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.get_cached_item('foo'),
            second=None)

    def test_add_cached_item(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.add_cached_item('foo', 'bar'),
            second=None)
