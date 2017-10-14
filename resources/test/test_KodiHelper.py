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

    def test_show_rating_dialog(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_rating_dialog(),
            second='')

    def test_show_adult_pin_dialog(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_adult_pin_dialog(),
            second='')

    def test_show_search_term_dialog(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_search_term_dialog(),
            second=None)

    @mock.patch('xbmcgui.Dialog.input')
    def test_show_search_term_dialog_not_empty(self, mock_dialog_input):
        """ADD ME"""
        mock_dialog_input.return_value = 'a'
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_search_term_dialog(),
            second='a')

    def test_show_add_to_library_title_dialog(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_add_to_library_title_dialog('foo'),
            second='foo')

    def test_show_add_to_library_title_dialog_orig(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        kodi_helper.custom_export_name = 'true'
        self.assertEqual(
            first=kodi_helper.show_add_to_library_title_dialog('foo'),
            second='foo')

    def test_show_password_dialog(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_password_dialog(),
            second='')

    def test_show_email_dialog(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_email_dialog(),
            second='')

    def test_show_login_failed_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_login_failed_notification(),
            second=None)

    def test_show_wrong_adult_pin_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_wrong_adult_pin_notification(),
            second=None)

    def test_show_missing_inputstream_addon_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_missing_inputstream_addon_notification(),
            second=None)

    def test_show_disabled_inputstream_addon_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_disabled_inputstream_addon_notification(),
            second=None)

    def test_show_no_search_results_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_no_search_results_notification(),
            second=None)

    def test_show_no_seasons_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_no_seasons_notification(),
            second=None)

    def test_request_error_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_request_error_notification(),
            second=None)

    def test_show_finally_remove(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_finally_remove(title='', type='', year=''),
            second=True)

    def test_show_finally_remove_with_year(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_finally_remove(title='', type='', year='0000'),
            second=True)

    def test_show_local_db_updated(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_local_db_updated(),
            second=None)

    def test_show_no_metadata_notification(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_no_metadata_notification(),
            second=None)

    def test_show_autologin_enabled(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.show_autologin_enabled(),
            second=None)

    def test_refresh(self):
        """ADD ME"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.refresh(),
            second=None)
