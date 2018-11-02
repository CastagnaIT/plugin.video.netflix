# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=wrong-import-position
"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import sys
import xbmcplugin

# Import and intiliaze globals right away to avoid stale values from the last
# addon invocation. Otherwise Kodi's reuseLanguageInvoker will caus some
# really quirky behavior!
from resources.lib.globals import g
g.init_globals(sys.argv)

import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.kodi.ui as ui
import resources.lib.navigation as nav
import resources.lib.navigation.directory as directory
import resources.lib.navigation.hub as hub
import resources.lib.navigation.player as player
import resources.lib.navigation.actions as actions
import resources.lib.navigation.library as library

NAV_HANDLERS = {
    g.MODE_DIRECTORY: directory.DirectoryBuilder,
    g.MODE_ACTION: actions.AddonActionExecutor,
    g.MODE_LIBRARY: library.LibraryActionExecutor,
    g.MODE_HUB: hub.HubBrowser
}


def route(pathitems):
    """Route to the appropriate handler"""
    common.debug('Routing navigation request')
    root_handler = pathitems[0] if pathitems else g.MODE_DIRECTORY
    if root_handler == g.MODE_PLAY:
        player.play(pathitems=pathitems[1:])
    else:
        try:
            nav.execute(NAV_HANDLERS[root_handler], pathitems[1:],
                        g.REQUEST_PARAMS)
        except KeyError:
            raise nav.InvalidPathError(
                'No root handler for path {}'.format('/'.join(pathitems)))


if __name__ == '__main__':
    # pylint: disable=broad-except
    # Initialize variables in common module scope
    # (necessary when reusing language invoker)
    common.info('Started (Version {})'.format(g.VERSION))
    common.info('URL is {}'.format(g.URL))

    try:
        route(filter(None, g.PATH.split('/')))
    except Exception as exc:
        import traceback
        common.error(traceback.format_exc())
        ui.show_error_info(title=common.get_local_string(30105),
                           message=': '.join((exc.__class__.__name__,
                                              exc.message)),
                           netflix_error=False)
        xbmcplugin.endOfDirectory(handle=g.PLUGIN_HANDLE, succeeded=False)

    cache.commit()
