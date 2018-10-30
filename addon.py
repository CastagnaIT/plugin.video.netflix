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

import resources.lib.cache as cache
import resources.lib.common as common
import resources.lib.kodi.ui as ui
import resources.lib.navigation as nav
import resources.lib.navigation.directory as directory
import resources.lib.navigation.hub as hub
import resources.lib.navigation.player as player
import resources.lib.navigation.actions as actions
import resources.lib.navigation.library as library

NAV_HANDLERS = {
    common.MODE_DIRECTORY: directory.DirectoryBuilder,
    common.MODE_ACTION: actions.AddonActionExecutor,
    common.MODE_LIBRARY: library.LibraryActionExecutor,
    common.MODE_HUB: hub.HubBrowser
}


def route(pathitems):
    """Route to the appropriate handler"""
    common.debug('Routing navigation request')
    root_handler = pathitems[0] if pathitems else common.MODE_DIRECTORY
    if root_handler == common.MODE_PLAY:
        player.play(pathitems=pathitems[1:])
    else:
        try:
            nav.execute(NAV_HANDLERS[root_handler], pathitems[1:],
                        common.REQUEST_PARAMS)
        except KeyError:
            raise nav.InvalidPathError(
                'No root handler for path {}'.format('/'.join(pathitems)))


if __name__ == '__main__':
    # Initialize variables in common module scope
    # (necessary when reusing language invoker)
    common.init_globals(sys.argv)
    common.info('Started (Version {})'.format(common.VERSION))
    common.info('URL is {}'.format(common.URL))

    try:
        route(filter(None, common.PATH.split('/')))
    except Exception as exc:
        import traceback
        common.error(traceback.format_exc())
        ui.show_notification(msg='Error: {}'.format(exc))
        xbmcplugin.endOfDirectory(handle=common.PLUGIN_HANDLE, succeeded=False)

    cache.commit()
