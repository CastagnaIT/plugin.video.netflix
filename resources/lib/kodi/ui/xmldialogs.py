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
from platform import machine

import xbmc
import xbmcgui

from resources.lib.globals import g
from resources.lib.kodi.ui.dialogs import (show_ok_dialog, show_error_info)

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

OS_MACHINE = machine()

CMD_CLOSE_DIALOG_BY_NOOP = 'AlarmClock(closedialog,Action(noop),{},silent)'


def show_modal_dialog(dlg_class, xml, path, **kwargs):
    """
    Show a modal Dialog in the UI.
    Pass kwargs minutes and/or seconds to have the dialog automatically
    close after the specified time.
    """
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

        if OS_MACHINE[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

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
        self.current_pin = kwargs.get('pin')
        self.maturity_levels = kwargs['maturity_levels']
        self.maturity_names = kwargs['maturity_names']
        self.current_level = kwargs['current_level']
        self.levels_count = len(self.maturity_levels)
        self.maturity_level_edge = {
            0: g.ADDON.getLocalizedString(30108),
            self.levels_count - 1: g.ADDON.getLocalizedString(30107)
        }
        self.status_base_desc = g.ADDON.getLocalizedString(30233)
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if OS_MACHINE[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

    def onInit(self):
        self._generate_levels_labels()
        # Set maturity level status description
        self._update_status_desc(self.current_level)
        # PIN input
        edit_control = self.getControl(10002)
        edit_control.setType(xbmcgui.INPUT_TYPE_NUMBER, g.ADDON.getLocalizedString(30002))
        edit_control.setText(self.current_pin)
        # Maturity level slider
        slider_control = self.getControl(10004)
        # setInt(value, min, delta, max)
        slider_control.setInt(self.current_level, 0, 1, self.levels_count - 1)

    def onClick(self, controlID):
        if controlID == 10028:  # Save and close dialog
            pin = self.getControl(10002).getText()
            # Validate pin length
            if not self._validate_pin(pin):
                return
            import resources.lib.api.shakti as api
            data = {'pin': pin,
                    'maturity_level': self.maturity_levels[self.current_level]['value']}
            # Send changes to the service
            if not api.set_parental_control_data(data).get('success', False):
                # Only in case of service problem
                show_error_info('Parental control saving', 'Error cannot save settings',
                                False, True)
            # I make sure that the metadata are removed,
            # otherwise you get inconsistencies with the request of the pin
            from resources.lib.cache import CACHE_METADATA
            g.CACHE.invalidate(True, [CACHE_METADATA])
            self.close()
        if controlID in [10029, 100]:  # Close dialog
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()
            return
        # Bad thing to check for changes in this way, but i have not found any other ways
        slider_value = self.getControl(10004).getInt()
        if slider_value != self.current_level:
            self._update_status_desc(slider_value)

    def _update_status_desc(self, maturity_level):
        self.current_level = \
            maturity_level if maturity_level else self.getControl(10004).getInt()
        if self.current_level == 0 or self.current_level == self.levels_count - 1:
            status_desc = self.maturity_level_edge[self.current_level]
        else:
            ml_included = [self.maturity_names[n]['name'] for n in
                           range(self.current_level, self.levels_count - 1)]
            status_desc = self.status_base_desc.format(', '.join(ml_included))
        self.getControl(10009).setLabel(status_desc)
        # Update labels color
        for ml in range(0, self.levels_count - 1):
            maturity_name = self.maturity_names[ml]['name'] + self.maturity_names[ml]['rating']
            ml_label = '[COLOR red]{}[/COLOR]'.format(maturity_name) \
                if ml in range(self.current_level, self.levels_count - 1) else maturity_name
            self.controls[ml].setLabel(ml_label)

    def _validate_pin(self, pin_value):
        if len(pin_value or '') != 4:
            show_ok_dialog('PIN', g.ADDON.getLocalizedString(30106))
            return False
        return True

    def _generate_levels_labels(self):
        """Generate descriptions for the levels dynamically"""
        # Limit to 1050 px max (to slider end)
        width = int(1050 / (self.levels_count - 1))
        height = 100
        pos_x = 275
        pos_y = 668
        self.controls = {}
        for lev_n in range(0, self.levels_count - 1):
            current_x = pos_x + (width * lev_n)
            maturity_name = self.maturity_names[lev_n]['name'] + \
                self.maturity_names[lev_n]['rating']
            lbl = xbmcgui.ControlLabel(current_x, pos_y, width, height, maturity_name,
                                       font='font12',
                                       alignment=XBFONT_CENTER_X)
            self.controls.update({lev_n: lbl})
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
        if OS_MACHINE[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

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
            from resources.lib.api.shakti import rate_thumb
            rate_thumb(self.videoid, rating_value, self.track_id_jaw)
            self.close()
        if controlID in [10040, 100]:  # Close
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()
