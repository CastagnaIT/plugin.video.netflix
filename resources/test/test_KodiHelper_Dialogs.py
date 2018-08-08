# -*- coding: utf-8 -*-
# Module: KodiHelper.Dialogs
# Author: asciidisco
# Created on: 11.10.2017
# License: MIT https://goo.gl/5bMj3H

"""Tests for the `KodiHelper.Dialogs` module"""

import unittest
import mock
from resources.lib.KodiHelper import KodiHelper
from resources.lib.ui.Dialogs import Dialogs


class KodiHelperDialogsTestCase(unittest.TestCase):
    """Tests for the `KodiHelper.Dialogs` module"""

    def test_show_rating_dialog(self):
        """Can call rating dialog"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_rating_dialog(),
            second='')

    def test_show_adult_pin_dialog(self):
        """Can call adult pin dialog"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_adult_pin_dialog(),
            second='')

    def test_show_search_term_dialog(self):
        """Can call input search term dialog (without value)"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_search_term_dialog(),
            second=None)

    @mock.patch('xbmcgui.Dialog.input')
    def test_show_search_term_dialog_with_value(self, mock_dialog_input):
        """Can call input search term dialog (with value)"""
        mock_dialog_input.return_value = 'a'
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_search_term_dialog(),
            second='a')

    def test_show_add_to_library_title_dialog(self):
        """Can call input library title dialog (without export)"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_add_library_title_dialog(
                original_title='foo'),
            second='foo')

    def test_show_add_library_title_dialog_export_true(self):
        """Can call input library title dialog (with export)"""
        kodi_helper = KodiHelper()
        kodi_helper.dialogs.custom_export_name = 'true'
        self.assertEqual(
            first=kodi_helper.dialogs.show_add_library_title_dialog(
                original_title='foo'),
            second='foo')

    def test_show_password_dialog(self):
        """Can call input password dialog"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_password_dialog(),
            second='')

    def test_show_email_dialog(self):
        """Can call input email dialog"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_email_dialog(),
            second='')

    def test_show_login_failed_notify(self):
        """Can call login failed notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_login_failed_notify(),
            second=None)

    def test_show_request_error_notify(self):
        """Can call request error notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_request_error_notify(),
            second=None)

    def test_show_is_missing_notify(self):
        """Can call inputstream not installed notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_is_missing_notify(),
            second=None)

    def test_show_no_search_results_notify(self):
        """Can call no search results notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_no_search_results_notify(),
            second=None)

    def test_show_is_inactive_notify(self):
        """Can call inputstream inactive (disabled) notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_is_inactive_notify(),
            second=None)

    def test_show_invalid_pin_notify(self):
        """Can call invalid adult pin notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_invalid_pin_notify(),
            second=None)

    def test_show_no_seasons_notify(self):
        """Can call no seasons available notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_no_seasons_notify(),
            second=None)

    def test_show_db_updated_notify(self):
        """Can call local db update notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_db_updated_notify(),
            second=None)

    def test_show_no_metadata_notify(self):
        """Can call no metadata notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_no_metadata_notify(),
            second=None)

    def test_show_autologin_enabled_notify(self):
        """Can call autologin enabled notification"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_autologin_enabled_notify(),
            second=None)

    def test_show_finally_remove_modal(self):
        """Can call finally remove from exported db modal"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_finally_remove_modal(title='foo', year='2015'),
            second=True)

    def test_show_finally_remove_modal_with_empty_year(self):
        """Can call finally remove from exported db modal with default year"""
        kodi_helper = KodiHelper()
        self.assertEqual(
            first=kodi_helper.dialogs.show_finally_remove_modal(title='foo'),
            second=True)
