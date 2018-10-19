# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=broad-except

"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import sys

import xbmcplugin

import resources.lib.common as common
from resources.lib.navigation import InvalidPathError
import resources.lib.navigation.directory as directory
import resources.lib.navigation.hub as hub
import resources.lib.api.shakti as api
import resources.lib.api.cache as cache
import resources.lib.kodi.ui as ui

def open_settings(addon_id):
    """Open settings page of another addon"""
    from xbmcaddon import Addon
    Addon(addon_id).openSettings()

def route(pathitems):
    """Route to the appropriate handler"""
    common.debug('Routing navigation request')
    if not common.PATH or pathitems[0] == common.MODE_DIRECTORY:
        directory.build(pathitems[1:], common.REQUEST_PARAMS)
    elif pathitems[0] == common.MODE_HUB:
        hub.browse(pathitems[1:], common.REQUEST_PARAMS)
    elif pathitems[0] == 'logout':
        api.logout()
    elif pathitems[0] == 'opensettings':
        try:
            open_settings(pathitems[1])
        except IndexError:
            raise InvalidPathError('Missing target addon id.')
    else:
        raise InvalidPathError('No root handler for path {}'
                               .format('/'.join(pathitems)))

if __name__ == '__main__':
    # Initialize variables in common module scope
    # (necessary when reusing language invoker)
    common.init_globals(sys.argv)
    common.info('Started (Version {})'.format(common.VERSION))
    common.info('URL is {}'.format(common.URL))

    try:
        route(common.PATH.split('/'))
    except Exception as exc:
        import traceback
        common.error(traceback.format_exc())
        ui.show_notification(title='An error occurred', msg=exc)
        xbmcplugin.endOfDirectory(handle=common.PLUGIN_HANDLE, succeeded=False)

    cache.commit()
