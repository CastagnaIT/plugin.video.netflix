# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import sys

import resources.lib.common as common
import resources.lib.navigation.directory as directory
import resources.lib.navigation.hub as hub
import resources.lib.api.shakti as api

def open_settings(addon_id):
    """Open settings page of another addon"""
    from xbmcaddon import Addon
    Addon(addon_id).openSettings()

if __name__ == '__main__':
    common.init_globals(sys.argv)
    common.info('Started (Version {})'.format(common.VERSION))
    common.info('URL is {}'.format(common.URL))
    # Path starts with / so we need to omit empty string at index 0
    PATH_ITEMS = common.PATH.split('/')

    # route to the appropriate navigation module based on first path item
    if not common.PATH or PATH_ITEMS[0] == common.MODE_DIRECTORY:
        directory.build(PATH_ITEMS[1:], common.REQUEST_PARAMS)
    elif PATH_ITEMS[0] == common.MODE_HUB:
        hub.browse(PATH_ITEMS[1:], common.REQUEST_PARAMS)
    elif PATH_ITEMS[0] == 'logout':
        api.logout()
    elif PATH_ITEMS[0] == 'opensettings':
        try:
            open_settings(PATH_ITEMS[1])
        except IndexError:
            common.error('Cannot open settings. Missing target addon id.')
    else:
        common.error('Invalid path: {}'.format(common.PATH))
