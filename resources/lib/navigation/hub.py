# -*- coding: utf-8 -*-
"""Navigation for hub mode - needs skin support!"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.api.shakti as api


class HubBrowser(object):
    """Fills window properties for browsing the Netflix style Hub"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing hub browser: {}'.format(params))
        self.params = params

        profile_id = params.get('profile_id')
        if profile_id:
            api.activate_profile(profile_id)

    def browse(self, pathitems):
        """Browse the hub at a given location"""
        pass
