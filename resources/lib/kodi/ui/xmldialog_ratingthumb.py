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
ACTION_NOOP = 999


# pylint: disable=invalid-name,no-member
class RatingThumb(xbmcgui.WindowXMLDialog):
    """Dialog for rating a tv show or movie"""

    def __init__(self, *args, **kwargs):
        self.videoid = kwargs['videoid']
        self.track_id_jaw = kwargs['track_id_jaw']
        self.title = kwargs.get('title', '--')
        self.user_rating = kwargs.get('user_rating', 0)
        # Netflix user rating thumb values
        # 0 = No rated
        # 1 = thumb down
        # 2 = thumb up
        self.action_exit_keys_id = [ACTION_PREVIOUS_MENU,
                                    ACTION_PLAYER_STOP,
                                    ACTION_NAV_BACK]
        super().__init__(*args)

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

    def onClick(self, controlId):
        if controlId in [10010, 10020, 10012, 10022]:  # Rating and close
            rating_map = {10010: 2, 10020: 1, 10012: 0, 10022: 0}
            rating_value = rating_map[controlId]
            from resources.lib.utils.api_requests import rate_thumb
            rate_thumb(self.videoid, rating_value, self.track_id_jaw)
            self.close()
        if controlId in [10040, 100]:  # Close
            self.close()

    def onAction(self, action):
        if action.getId() in self.action_exit_keys_id:
            self.close()
