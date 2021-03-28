# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    XML based dialog

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import xbmcgui

ACTION_PREVIOUS_MENU = 10
ACTION_PLAYER_STOP = 13
ACTION_NAV_BACK = 92


# pylint: disable=invalid-name,no-member
class Profiles(xbmcgui.WindowXMLDialog):
    """Dialog for profile selection"""

    def __init__(self, *args, **kwargs):
        self.ctrl_list = None
        self.return_value = None
        self.title = kwargs['title']
        self.dir_items = kwargs['dir_items']
        self.preselect_guid = kwargs.get('preselect_guid')
        self.action_exit_keys_id = [ACTION_PREVIOUS_MENU,
                                    ACTION_PLAYER_STOP,
                                    ACTION_NAV_BACK]
        super().__init__(*args)

    def onInit(self):
        # Keep only the ListItem objects
        list_items = [list_item for (_, list_item, _) in self.dir_items]
        self.getControl(99).setLabel(self.title)
        self.ctrl_list = self.getControl(10001)
        self.ctrl_list.addItems(list_items)
        # Preselect the ListItem by guid
        self.ctrl_list.selectItem(0)
        if self.preselect_guid:
            for index, list_item in enumerate(list_items):
                if list_item.getProperty('nf_guid') == self.preselect_guid:
                    self.ctrl_list.selectItem(index)
                    break
        self.setFocusId(10001)

    def onClick(self, controlId):
        if controlId == 10001:  # Save and close dialog
            sel_list_item = self.ctrl_list.getSelectedItem()
            # 'nf_guid' property is set to Listitems from _create_profile_item of dir_builder_items.py
            self.return_value = sel_list_item.getProperty('nf_guid')
            self.close()
        if controlId in [10029, 100]:  # Close
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exit_keys_id:
            self.close()
