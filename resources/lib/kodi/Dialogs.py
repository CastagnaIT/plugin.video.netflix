# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: Dialogs
# Created on: 16.10.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi UI Dialogs"""

import xbmcgui


class Dialogs(object):
    """Kodi UI Dialogs"""

    def __init__(self, get_local_string, custom_export_name, notify_time=5000):
        """
        Sets the i18n string loader function and exprt name properties

        :param original_title: Original title of the show
        :type original_title: str
        """
        self.notify_time = notify_time
        self.get_local_string = get_local_string
        self.custom_export_name = custom_export_name

    def show_rating_dialog(self):
        """
        Asks the user for a movie rating

        :returns: int - Movie rating between 0 & 10
        """
        dlg = xbmcgui.Dialog()
        heading = self.get_local_string(string_id=30019)
        heading += ' '
        heading += self.get_local_string(string_id=30022)
        return dlg.numeric(heading=heading, type=0)

    def show_adult_pin_dialog(self):
        """
        Asks the user for the adult pin

        :returns: int - 4 digit adult pin needed for adult movies
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.input(
            heading=self.get_local_string(string_id=30002),
            type=xbmcgui.INPUT_NUMERIC)
        return dialog

    def show_search_term_dialog(self):
        """
        Asks the user for a term to query the netflix search for

        :returns: str - Term to search for
        """
        dlg = xbmcgui.Dialog()
        term = dlg.input(
            heading=self.get_local_string(string_id=30003),
            type=xbmcgui.INPUT_ALPHANUM)
        if len(term) == 0:
            term = None
        return term

    def show_add_library_title_dialog(self, original_title):
        """
        Asks the user for an alternative title for the show/movie that
        gets exported to the local library

        :param original_title: Original title of the show
        :type original_title: str

        :returns: str - Title to persist
        """
        if self.custom_export_name == 'true':
            return original_title
        dlg = xbmcgui.Dialog()
        custom_title = dlg.input(
            heading=self.get_local_string(string_id=30031),
            defaultt=original_title,
            type=xbmcgui.INPUT_ALPHANUM) or original_title
        return original_title or custom_title

    def show_password_dialog(self):
        """
        Asks the user for its Netflix password

        :returns: str - Netflix password
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.input(
            heading=self.get_local_string(string_id=30004),
            type=xbmcgui.INPUT_ALPHANUM,
            option=xbmcgui.ALPHANUM_HIDE_INPUT)
        return dialog

    def show_email_dialog(self):
        """
        Asks the user for its Netflix account email

        :returns: str - Netflix account email
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.input(
            heading=self.get_local_string(string_id=30005),
            type=xbmcgui.INPUT_ALPHANUM)
        return dialog

    def show_login_failed_notify(self):
        """
        Shows notification that the login failed

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=30008),
            message=self.get_local_string(string_id=30009),
            icon=xbmcgui.NOTIFICATION_ERROR,
            time=self.notify_time)
        return dialog

    def show_request_error_notify(self):
        """
        Shows notification that a request error occured

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=30051),
            message=self.get_local_string(string_id=30052),
            icon=xbmcgui.NOTIFICATION_ERROR,
            time=self.notify_time)
        return dialog

    def show_invalid_pin_notify(self):
        """
        Shows notification that a wrong adult pin was given

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=30006),
            message=self.get_local_string(string_id=30007),
            icon=xbmcgui.NOTIFICATION_ERROR,
            time=self.notify_time)
        return dialog

    def show_no_search_results_notify(self):
        """
        Shows notification that no search results could be found

        :return: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=30011),
            message=self.get_local_string(string_id=30013),
            icon=xbmcgui.NOTIFICATION_INFO,
            time=self.notify_time)
        return dialog

    def show_no_seasons_notify(self):
        """
        Shows notification that no seasons be found

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=30010),
            message=self.get_local_string(string_id=30012),
            icon=xbmcgui.NOTIFICATION_INFO,
            time=self.notify_time)
        return dialog

    def show_db_updated_notify(self):
        """
        Shows notification that local db was updated

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=15101),
            message=self.get_local_string(string_id=30050),
            icon=xbmcgui.NOTIFICATION_INFO,
            time=self.notify_time)
        return dialog

    def show_no_metadata_notify(self):
        """
        Shows notification that no metadata is available

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=14116),
            message=self.get_local_string(string_id=195),
            icon=xbmcgui.NOTIFICATION_INFO,
            time=self.notify_time)
        return dialog

    def show_episodes_added_notify(self, showtitle, episodes, icon):
        """
        Shows notification that new episodes were added to the library

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=showtitle,
            message='{} {}'.format(episodes,
                                   self.get_local_string(string_id=30063)),
            icon=icon,
            time=self.notify_time)
        return dialog

    def show_autologin_enabled_notify(self):
        """
        Shows notification that auto login is enabled

        :returns: bool - Dialog shown
        """
        dlg = xbmcgui.Dialog()
        dialog = dlg.notification(
            heading=self.get_local_string(string_id=14116),
            message=self.get_local_string(string_id=30058),
            icon=xbmcgui.NOTIFICATION_INFO,
            time=self.notify_time)
        return dialog

    def show_finally_remove_modal(self, title, year='0000'):
        """
        Ask if user wants to remove the item from the local library

        :param title: Title of the show
        :type title: str
        :param year: Year of the show
        :type year: str

        :returns: bool - Answer yes/no
        """
        dlg = xbmcgui.Dialog()
        if year == '0000':
            dialog = dlg.yesno(
                heading=self.get_local_string(string_id=30047),
                line1=title)
            return dialog
        dialog = dlg.yesno(
            heading=self.get_local_string(string_id=30047),
            line1=title + ' (' + str(year) + ')')
        return dialog
