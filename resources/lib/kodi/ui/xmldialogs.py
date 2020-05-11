# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    XML based dialogs

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
# pylint: disable=invalid-name,missing-docstring,attribute-defined-outside-init
from __future__ import absolute_import, division, unicode_literals

import time

import xbmc
import xbmcgui

from resources.lib.common import run_threaded, get_machine, make_call
from resources.lib.globals import g
from resources.lib.kodi.ui.dialogs import show_error_info

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92
ACTION_NOOP = 999

XBFONT_LEFT = 0x00000000
XBFONT_RIGHT = 0x00000001
XBFONT_CENTER_X = 0x00000002
XBFONT_CENTER_Y = 0x00000004
XBFONT_TRUNCATED = 0x00000008
XBFONT_JUSTIFY = 0x00000010

CMD_CLOSE_DIALOG_BY_NOOP = 'AlarmClock(closedialog,Action(noop),{},silent)'


# @time_execution(immediate=True)
def show_modal_dialog(non_blocking, dlg_class, xml, path, **kwargs):
    """
    Show a modal Dialog in the UI.
    Pass kwargs minutes and/or seconds to have the dialog automatically
    close after the specified time.

    :return if exists return self.return_value value of dlg_class (if non_blocking=True return always None)
    """
    # WARNING: doModal when invoked does not release the function immediately!
    # it seems that doModal waiting for all window operations to be completed before return,
    # for example the "Skip" dialog takes about 30 seconds to release the function (test on Kodi 19.x)
    # To be taken into account because it can do very big delays in the execution of the invoking code
    return run_threaded(non_blocking, _show_modal_dialog, dlg_class, xml, path, **kwargs)


def _show_modal_dialog(dlg_class, xml, path, **kwargs):
    dlg = dlg_class(xml, path, 'default', '1080i', **kwargs)
    minutes = kwargs.get('minutes', 0)
    seconds = kwargs.get('seconds', 0)
    if minutes > 0 or seconds > 0:
        # Bug in Kodi AlarmClock function, if only the seconds are passed
        # the time conversion inside the function multiply the seconds by 60
        if seconds > 59 and minutes == 0:
            alarm_time = time.strftime('%M:%S', time.gmtime(seconds))
        else:
            alarm_time = '{:02d}:{:02d}'.format(minutes, seconds)
        xbmc.executebuiltin(CMD_CLOSE_DIALOG_BY_NOOP.format(alarm_time))
    dlg.doModal()
    if hasattr(dlg, 'return_value'):
        return dlg.return_value
    return None


class Skip(xbmcgui.WindowXMLDialog):
    """
    Dialog for skipping video parts (intro, recap, ...)
    """
    def __init__(self, *args, **kwargs):
        self.skip_to = kwargs['skip_to']
        self.label = kwargs['label']

        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK,
                                   ACTION_NOOP]

        if get_machine()[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            try:
                xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                xbmcgui.WindowXMLDialog.__init__(self)

    def onInit(self):
        self.getControl(6012).setLabel(self.label)

    def onClick(self, controlID):
        if controlID == 6012:
            xbmc.Player().seekTime(self.skip_to)
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()


# pylint: disable=no-member
class ParentalControl(xbmcgui.WindowXMLDialog):
    """
    Dialog for parental control settings
    """
    def __init__(self, *args, **kwargs):
        # Keep pin option, there is still some reference in the netflix code
        # self.current_pin = kwargs.get('pin')
        self.data = kwargs['data']
        self.rating_levels = kwargs['rating_levels']
        self.current_maturity = self.data['maturity']
        self.current_level_index = kwargs['current_level_index']
        self.profile_info = self.data['profileInfo']
        self.levels_count = len(self.rating_levels)
        self.status_base_desc = g.ADDON.getLocalizedString(30233)
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if get_machine()[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            try:
                xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                xbmcgui.WindowXMLDialog.__init__(self)

    def onInit(self):
        self._generate_levels_labels()
        # Set maturity level status description
        self._update_status_desc(self.current_level_index)
        # Set profile name to label description
        self.getControl(10003).setLabel(g.ADDON.getLocalizedString(30232).format(self.profile_info['profileName']))
        # PIN input
        # edit_control = self.getControl(10002)
        # edit_control.setType(xbmcgui.INPUT_TYPE_NUMBER, g.ADDON.getLocalizedString(30002))
        # edit_control.setText(self.current_pin)
        # Maturity level slider
        slider_control = self.getControl(10004)
        # setInt(value, min, delta, max)
        slider_control.setInt(self.current_level_index, 0, 1, self.levels_count - 1)

    def onClick(self, controlID):
        if controlID == 10028:  # Save and close dialog
            # pin = self.getControl(10002).getText()
            # # Validate pin length
            # if not self._validate_pin(pin):
            #     return
            import resources.lib.api.api_requests as api
            data = {'guid': self.data['profileInfo']['guid'],
                    'experience': self.data['experience'],
                    'maturity': self.rating_levels[self.current_level_index]['value'],
                    'token': self.data['token']}
            # Send changes to the service
            if not api.set_parental_control_data(data):
                show_error_info('Parental controls', 'An error has occurred when saving data',
                                False, True)
            # I make sure that the metadata are removed,
            # otherwise you get inconsistencies with the request of the pin
            # from resources.lib.common.cache_utils import CACHE_METADATA
            # g.CACHE.clear([CACHE_METADATA])

            # The selection of the maturity level affects the lists data as a filter,
            # so you need to clear the lists in the cache in order not to create inconsistencies
            from resources.lib.common.cache_utils import CACHE_COMMON, CACHE_GENRES, CACHE_MYLIST, CACHE_SEARCH
            g.CACHE.clear([CACHE_COMMON, CACHE_GENRES, CACHE_MYLIST, CACHE_SEARCH])
            self.close()
        if controlID in [10029, 100]:  # Close dialog
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()
            return
        # Bad thing to check for changes in this way, but i have not found any other ways
        slider_value = self.getControl(10004).getInt()
        if slider_value != self.current_level_index:
            self._update_status_desc(slider_value)

    def _update_status_desc(self, new_level_index=None):
        self.current_level_index = self.getControl(10004).getInt() if new_level_index is None else new_level_index
        # Update labels color of slider steps
        for index in range(0, self.levels_count):
            maturity_name = '[' + self.rating_levels[index]['label'] + ']'
            ml_label = '[COLOR red]{}[/COLOR]'.format(maturity_name) if index <= self.current_level_index else maturity_name
            self.controls[index].setLabel(ml_label)
        # Update status description
        hint = self.rating_levels[self.current_level_index]['description']
        ml_labels_included = [self.rating_levels[index]['label'] for index in range(0, self.current_level_index + 1)]
        status_desc = self.status_base_desc.format(', '.join(ml_labels_included)) + '[CR]' + hint
        self.getControl(10009).setLabel(status_desc)

    # def _validate_pin(self, pin_value):
    #     if len(pin_value or '') != 4:
    #         show_ok_dialog('PIN', g.ADDON.getLocalizedString(30106))
    #         return False
    #     return True

    def _generate_levels_labels(self):
        """Generate descriptions for the levels dynamically"""
        # Limit to 1200 px max (should be longer than slider)
        width = int(1200 / self.levels_count)
        height = 100
        pos_x = 175
        pos_y = 508  # 668
        self.controls = {}
        for index, rating_level in enumerate(self.rating_levels):
            current_x = pos_x + (width * index)
            maturity_name = '[' + rating_level['label'] + ']'
            lbl = xbmcgui.ControlLabel(current_x, pos_y, width, height, maturity_name,
                                       font='font10',
                                       alignment=XBFONT_CENTER_X)
            self.controls.update({index: lbl})
            self.addControl(lbl)


# pylint: disable=no-member
class RatingThumb(xbmcgui.WindowXMLDialog):
    """
    Dialog for rating a tvshow or movie
    """
    def __init__(self, *args, **kwargs):
        self.videoid = kwargs['videoid']
        self.track_id_jaw = kwargs['track_id_jaw']
        self.title = kwargs.get('title', '--')
        self.user_rating = kwargs.get('user_rating', 0)
        # Netflix user rating thumb values
        # 0 = No rated
        # 1 = thumb down
        # 2 = thumb up
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if get_machine()[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            try:
                xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                xbmcgui.WindowXMLDialog.__init__(self)

    def onInit(self):
        self.getControl(10000).setLabel(self.title)
        # Kodi does not allow to change button textures in runtime
        # and you can not add nested controls via code,
        # so the only alternative is to create double XML buttons
        # and eliminate those that are not needed
        focus_id = 10010
        if self.user_rating == 0:  # No rated
            self.removeControl(self.getControl(10012))
            self.removeControl(self.getControl(10022))
        if self.user_rating == 1:  # Thumb down set
            self.removeControl(self.getControl(10012))
            self.removeControl(self.getControl(10020))
            self.getControl(10010).controlRight(self.getControl(10022))
            self.getControl(10040).controlLeft(self.getControl(10022))
        if self.user_rating == 2:  # Thumb up set
            focus_id = 10012
            self.removeControl(self.getControl(10010))
            self.removeControl(self.getControl(10022))
            self.getControl(10020).controlLeft(self.getControl(10012))
        self.setFocusId(focus_id)

    def onClick(self, controlID):
        if controlID in [10010, 10020, 10012, 10022]:  # Rating and close
            rating_map = {10010: 2, 10020: 1, 10012: 0, 10022: 0}
            rating_value = rating_map[controlID]
            from resources.lib.api.api_requests import rate_thumb
            rate_thumb(self.videoid, rating_value, self.track_id_jaw)
            self.close()
        if controlID in [10040, 100]:  # Close
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()


def show_profiles_dialog(title=None):
    """
    Show a dialog to select a profile

    :return guid of selected profile or None
    """
    # Get profiles data
    list_data, extra_data = make_call('get_profiles', {'request_update': True})  # pylint: disable=unused-variable
    return show_modal_dialog(False,
                             Profiles,
                             'plugin-video-netflix-Profiles.xml',
                             g.ADDON.getAddonInfo('path'),
                             title=title or g.ADDON.getLocalizedString(30128),
                             list_data=list_data)


# pylint: disable=no-member
class Profiles(xbmcgui.WindowXMLDialog):
    """
    Dialog for profile selection
    """
    def __init__(self, *args, **kwargs):
        self.ctrl_list = None
        self.return_value = None
        self.title = kwargs['title']
        self.list_data = kwargs['list_data']
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if get_machine()[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            try:
                xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)
            except Exception:  # pylint: disable=broad-except
                xbmcgui.WindowXMLDialog.__init__(self)

    def onInit(self):
        self.getControl(99).setLabel(self.title)
        self.ctrl_list = self.getControl(10001)
        from resources.lib.navigation.directory_utils import convert_list_to_list_items
        self.ctrl_list.addItems(convert_list_to_list_items(self.list_data))

    def onClick(self, controlID):
        if controlID == 10001:  # Save and close dialog
            sel_list_item = self.ctrl_list.getSelectedItem()
            # 'nf_guid' property is set to Listitems from _create_profile_item of dir_builder_items.py
            self.return_value = sel_list_item.getProperty('nf_guid')
            self.close()
        if controlID in [10029, 100]:  # Close
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()
