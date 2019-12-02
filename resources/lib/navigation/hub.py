# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation for hub mode

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.common as common
import resources.lib.api.shakti as api


# Needs skin support!
class HubBrowser(object):
    """Fills window properties for browsing the Netflix style Hub"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing hub browser: {}', params)
        self.params = params

        profile_id = params.get('profile_id')
        if profile_id:
            api.activate_profile(profile_id)

    def browse(self, pathitems):
        """Browse the hub at a given location"""
