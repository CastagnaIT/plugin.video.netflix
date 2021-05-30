# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    XML based dialog

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xbmcgui

from resources.lib.globals import G

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92
XBFONT_LEFT = 0x00000000
XBFONT_RIGHT = 0x00000001
XBFONT_CENTER_X = 0x00000002
XBFONT_CENTER_Y = 0x00000004
XBFONT_TRUNCATED = 0x00000008
XBFONT_JUSTIFY = 0x00000010


# pylint: disable=invalid-name,no-member
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
        self.status_base_desc = G.ADDON.getLocalizedString(30233)
        self.controls = {}
        self.action_exit_keys_id = [ACTION_PREVIOUS_MENU,
                                    ACTION_PLAYER_STOP,
                                    ACTION_NAV_BACK]
        super().__init__(*args)

    def onInit(self):
        self._generate_levels_labels()
        # Set maturity level status description
        self._update_status_desc(self.current_level_index)
        # Set profile name to label description
        self.getControl(10003).setLabel(G.ADDON.getLocalizedString(30232).format(self.profile_info['profileName']))
        # PIN input
        # edit_control = self.getControl(10002)
        # edit_control.setType(xbmcgui.INPUT_TYPE_NUMBER, G.ADDON.getLocalizedString(30002))
        # edit_control.setText(self.current_pin)
        # Maturity level slider
        slider_control = self.getControl(10004)
        # setInt(value, min, delta, max)
        slider_control.setInt(self.current_level_index, 0, 1, self.levels_count - 1)

    def onClick(self, controlId):
        if controlId == 10028:  # Save and close dialog
            # pin = self.getControl(10002).getText()
            # # Validate pin length
            # if not self._validate_pin(pin):
            #     return
            import resources.lib.utils.api_requests as api
            data = {'guid': self.data['profileInfo']['guid'],
                    'experience': self.data['experience'],
                    'maturity': self.rating_levels[self.current_level_index]['value'],
                    'token': self.data['token']}
            # Send changes to the service
            api.set_parental_control_data(data)

            # The selection of the maturity level affects the lists data as a filter,
            # so you need to clear the lists in the cache in order not to create inconsistencies
            from resources.lib.common.cache_utils import CACHE_COMMON, CACHE_GENRES, CACHE_MYLIST, CACHE_SEARCH
            G.CACHE.clear([CACHE_COMMON, CACHE_GENRES, CACHE_MYLIST, CACHE_SEARCH])
            self.close()
        if controlId in [10029, 100]:  # Close dialog
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exit_keys_id:
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
            maturity_name = f'[{self.rating_levels[index]["label"]}]'
            ml_label = f'[COLOR red]{maturity_name}[/COLOR]' if index <= self.current_level_index else maturity_name
            self.controls[index].setLabel(ml_label)
        # Update status description
        hint = self.rating_levels[self.current_level_index]['description']
        ml_labels_included = [self.rating_levels[index]['label'] for index in range(0, self.current_level_index + 1)]
        status_desc = self.status_base_desc.format(', '.join(ml_labels_included)) + f'[CR]{hint}'
        self.getControl(10009).setLabel(status_desc)

    # def _validate_pin(self, pin_value):
    #     if len(pin_value or '') != 4:
    #         show_ok_dialog('PIN', G.ADDON.getLocalizedString(30106))
    #         return False
    #     return True

    def _generate_levels_labels(self):
        """Generate descriptions for the levels dynamically"""
        # Limit to 1200 px max (should be longer than slider)
        width = int(1200 / self.levels_count)
        height = 100
        pos_x = 175
        pos_y = 508  # 668
        for index, rating_level in enumerate(self.rating_levels):
            current_x = pos_x + (width * index)
            maturity_name = f'[{rating_level["label"]}]'
            lbl = xbmcgui.ControlLabel(current_x, pos_y, width, height, maturity_name,
                                       font='font10',
                                       alignment=XBFONT_CENTER_X)
            self.controls.update({index: lbl})
            self.addControl(lbl)
