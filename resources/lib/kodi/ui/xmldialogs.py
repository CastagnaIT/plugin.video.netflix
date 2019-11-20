# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,missing-docstring,attribute-defined-outside-init
"""XML based dialogs"""
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


class ParentalControl(xbmcgui.WindowXMLDialog):
    """
    Dialog for parental control settings
    """
    def __init__(self, *args, **kwargs):
        # Convert slider value to Netflix maturity levels
        self.nf_maturity_levels = {
            0: 0,
            1: 41,
            2: 80,
            3: 100,
            4: 9999
        }
        self.current_pin = kwargs.get('pin')
        self.current_maturity_level = kwargs.get('maturity_level', 4)
        self.maturity_level_desc = {
            0: g.ADDON.getLocalizedString(30232),
            1: g.ADDON.getLocalizedString(30233),
            2: g.ADDON.getLocalizedString(30234),
            3: g.ADDON.getLocalizedString(30235),
            4: g.ADDON.getLocalizedString(30236)
        }
        self.maturity_level_edge = {
            0: g.ADDON.getLocalizedString(30108),
            4: g.ADDON.getLocalizedString(30107)
        }
        self.status_base_desc = g.ADDON.getLocalizedString(30237)
        self.action_exitkeys_id = [ACTION_PREVIOUS_MENU,
                                   ACTION_PLAYER_STOP,
                                   ACTION_NAV_BACK]
        if OS_MACHINE[0:5] == 'armv7':
            xbmcgui.WindowXMLDialog.__init__(self)
        else:
            xbmcgui.WindowXMLDialog.__init__(self, *args, **kwargs)

    def onInit(self):
        # Set maturity level status description
        self._update_status_desc(self.current_maturity_level)
        # PIN input
        edit_control = self.getControl(2)
        edit_control.setType(xbmcgui.INPUT_TYPE_NUMBER, g.ADDON.getLocalizedString(30002))
        edit_control.setText(self.current_pin)
        # Maturity level slider
        slider_control = self.getControl(4)
        # setInt(value, min, delta, max)
        slider_control.setInt(self.current_maturity_level, 0, 1, 4)

    def onClick(self, controlID):
        if controlID == 28:  # Save and close dialog
            pin = self.getControl(2).getText()
            # Validate pin length
            if not self._validate_pin(pin):
                return
            import resources.lib.api.shakti as api
            data = {'pin': pin,
                    'maturity_level': self.nf_maturity_levels[self.current_maturity_level]}
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
        if controlID in [29, 100]:  # Close dialog
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exitkeys_id:
            self.close()
            return
        # Bad thing to check for changes in this way, but i have not found any other ways
        slider_value = self.getControl(4).getInt()
        if slider_value != self.current_maturity_level:
            self._update_status_desc(slider_value)

    def _update_status_desc(self, maturity_level):
        self.current_maturity_level = \
            maturity_level if maturity_level else self.getControl(4).getInt()
        if self.current_maturity_level in self.maturity_level_edge:
            status_desc = self.maturity_level_edge[self.current_maturity_level]
        else:
            ml_included = [self.maturity_level_desc[n] for n in
                           range(self.current_maturity_level + 1, 5)]
            status_desc = self.status_base_desc.format(', '.join(ml_included))
        for ml in range(1, 5):
            ml_label = '[COLOR red]{}[/COLOR]'.format(self.maturity_level_desc[ml]) \
                if ml in range(self.current_maturity_level + 1, 5) else self.maturity_level_desc[ml]
            self.getControl(200 + ml).setLabel(ml_label)
        self.getControl(9).setLabel(status_desc)

    def _validate_pin(self, pin_value):
        if len(pin_value or '') != 4:
            show_ok_dialog('PIN', g.ADDON.getLocalizedString(30106))
            return False
        return True


class SaveStreamSettings(xbmcgui.WindowXMLDialog):
    """
    Dialog for skipping video parts (intro, recap, ...)
    """
    def __init__(self, *args, **kwargs):  # pylint: disable=super-on-old-class
        super(SaveStreamSettings, self).__init__(*args, **kwargs)
        self.new_show_settings = kwargs['new_show_settings']
        self.tvshowid = kwargs['tvshowid']
        self.storage = kwargs['storage']

    def onInit(self):
        self.action_exitkeys_id = [10, 13]

    def onClick(self, controlID):
        if controlID == 6012:
            self.storage[self.tvshowid] = self.new_show_settings
            self.close()
