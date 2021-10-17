# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Various simple dialogs

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xbmc
import xbmcgui

from resources.lib.globals import G
import resources.lib.common as common


def show_notification(msg, title='Netflix', time=3000):
    """Show a notification"""
    xbmc.executebuiltin(f'Notification({title}, {msg}, {time}, {G.ICON})')


def ask_credentials():
    """
    Show some dialogs and ask the user for account credentials
    """
    email = xbmcgui.Dialog().input(
        heading=common.get_local_string(30005),
        type=xbmcgui.INPUT_ALPHANUM) or None
    common.verify_credentials(email)
    password = ask_for_password()
    common.verify_credentials(password)
    return {
        'email': email.strip(),
        'password': password.strip()
    }


def ask_for_password():
    """Ask the user for the password"""
    return xbmcgui.Dialog().input(
        heading=common.get_local_string(30004),
        type=xbmcgui.INPUT_ALPHANUM,
        option=xbmcgui.ALPHANUM_HIDE_INPUT) or None


def ask_for_rating():
    """Ask the user for a rating"""
    heading = f'{common.get_local_string(30019)} {common.get_local_string(30022)}'
    try:
        return int(xbmcgui.Dialog().numeric(heading=heading, type=0,
                                            defaultt=''))
    except ValueError:
        return None


def show_dlg_input_numeric(message, mask_input=True):
    """Ask the user to enter numbers"""
    args = {'heading': message,
            'type': 0,
            'defaultt': '',
            'bHiddenInput': mask_input}
    return xbmcgui.Dialog().numeric(**args) or None


def ask_for_search_term(default_text=None):
    """Ask the user for a search term"""
    return ask_for_input(common.get_local_string(30402), default_text)


def ask_for_input(heading, default_text=None):
    return xbmcgui.Dialog().input(
        defaultt=default_text,
        heading=heading,
        type=xbmcgui.INPUT_ALPHANUM) or None


def ask_for_confirmation(title, message):
    """Ask the user to confirm an operation"""
    return xbmcgui.Dialog().yesno(title, message)


def ask_for_resume(resume_position):
    """Ask the user for resuming a video"""
    return xbmcgui.Dialog().contextmenu(
        [
            common.get_local_string(12022).format(common.convert_seconds_to_hms_str(resume_position)),
            common.get_local_string(12021)
        ])


def show_backend_not_ready(error_details=None):
    message = common.get_local_string(30138)
    if error_details:
        message += f'[CR][CR]Error details:[CR]{error_details}'
    return xbmcgui.Dialog().ok(common.get_local_string(30105), message)


def show_ok_dialog(title, message):
    return xbmcgui.Dialog().ok(title, message)


def show_yesno_dialog(title, message, yeslabel=None, nolabel=None, default_yes_button=False):
    if G.KODI_VERSION < '20':
        return xbmcgui.Dialog().yesno(title, message, yeslabel=yeslabel, nolabel=nolabel)
    # pylint: disable=no-member,unexpected-keyword-arg
    default_button = xbmcgui.DLG_YESNO_YES_BTN if default_yes_button else xbmcgui.DLG_YESNO_NO_BTN
    return xbmcgui.Dialog().yesno(title, message,
                                  yeslabel=yeslabel, nolabel=nolabel, defaultbutton=default_button)


def show_error_info(title, message, unknown_error=False, netflix_error=False):
    """Show a dialog that displays the error message"""
    prefix = (30104, 30102, 30101)[unknown_error + netflix_error]
    return xbmcgui.Dialog().ok(title, (common.get_local_string(prefix) + '[CR]' +
                                       message + '[CR][CR]' +
                                       common.get_local_string(30103)))


def show_addon_error_info(exc):
    """Show a dialog to notify of an addon internal error"""
    show_error_info(title=common.get_local_string(30105),
                    message=': '.join((exc.__class__.__name__, str(exc))),
                    netflix_error=False)


def show_library_task_errors(notify_errors, errors):
    if notify_errors and errors:
        xbmcgui.Dialog().ok(common.get_local_string(0),
                            '[CR]'.join([f'{err["title"]} ({err["error"]})'
                                         for err in errors]))


def show_browse_dialog(title, browse_type=0, default_path=None, multi_selection=False, extensions=None):
    """
    Show a browse dialog to select files or folders
    :param title: The window title
    :param browse_type: Type of dialog as int value (0 = ShowAndGetDirectory, 1 = ShowAndGetFile, ..see doc)
    :param default_path: The initial path
    :param multi_selection: Allow multi selection
    :param extensions: extensions allowed e.g. '.jpg|.png'
    :return: The selected path as string (or tuple of selected items) if user pressed 'Ok', else None
    """
    ret = xbmcgui.Dialog().browse(browse_type, title, shares='', useThumbs=False, treatAsFolder=False,
                                  defaultt=default_path, enableMultiple=multi_selection, mask=extensions)
    # Note: when defaultt is set and the user cancel the action (when enableMultiple is False),
    #       will be returned the defaultt value again, so we avoid this strange behavior...
    return None if not ret or ret == default_path else ret


def show_dlg_select(title, item_list):
    """
    Show a select dialog for a list of objects

    :return index of selected item, or -1 when cancelled
    """
    return xbmcgui.Dialog().select(title, item_list)


class ProgressDialog(xbmcgui.DialogProgress):
    """Context manager to handle a progress dialog window"""
    # Keep the same arguments for all progress bar classes
    def __init__(self, is_enabled, title=None, initial_value=0, max_value=1):
        super().__init__()
        self.is_enabled = is_enabled
        self.max_value = max_value
        self.value = initial_value
        self._percent = int(initial_value * 100 / max_value) if max_value else 0
        if is_enabled:
            self.create(title or common.get_local_string(30047))

    def __enter__(self):
        if self.is_enabled:
            self.update(self._percent, common.get_local_string(261))  # "Waiting for start..."
        return self

    def set_message(self, message):
        if self.is_enabled:
            self.update(self._percent, message)

    def set_wait_message(self):
        if self.is_enabled:
            self.update(self._percent, common.get_local_string(20186))  # "Please wait"

    def is_cancelled(self):
        """Return True when the user has pressed cancel button"""
        return self.is_enabled and self.iscanceled()

    def perform_step(self):
        self.value += 1
        self._percent = int(self.value * 100 / self.max_value)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.is_enabled:
            self.close()


class ProgressBarBG(xbmcgui.DialogProgressBG):
    """Context manager to handle a progress bar in background"""
    # Keep the same arguments for all progress bar classes
    def __init__(self, is_enabled, title, initial_value=None, max_value=None):
        super().__init__()
        self.is_enabled = is_enabled
        self.max_value = max_value
        self.value = 0 if max_value and initial_value is None else initial_value
        self._percent = int(initial_value * 100 / max_value) if initial_value and max_value else None
        if is_enabled:
            self.create(title)

    def __enter__(self):
        if self.is_enabled:
            self._update(common.get_local_string(261))  # "Waiting for start..."
        return self

    def set_message(self, message):
        if self.is_enabled:
            self._update(message)

    def set_wait_message(self):
        if self.is_enabled:
            self._update(common.get_local_string(20186))  # "Please wait"

    def perform_step(self):
        self.value += 1
        self._percent = int(self.value * 100 / self.max_value)

    def _update(self, message):
        kwargs = {'message': message}
        if self._percent is not None:
            kwargs['percent'] = self._percent
        self.update(**kwargs)  # Here all the arguments are optionals

    def is_cancelled(self):
        # Not supported - only need to ensure consistency in dynamic class management
        return False

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.is_enabled:
            self.close()
