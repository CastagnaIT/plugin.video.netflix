# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=wrong-import-position
"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import sys
from functools import wraps

import xbmcplugin

# Import and initialize globals right away to avoid stale values from the last
# addon invocation. Otherwise Kodi's reuseLanguageInvoker will cause some
# really quirky behavior!
from resources.lib.globals import g
g.init_globals(sys.argv)

import resources.lib.common as common
import resources.lib.upgrade_controller as upgrade_ctrl
import resources.lib.api.shakti as api
import resources.lib.kodi.ui as ui
import resources.lib.navigation as nav
import resources.lib.navigation.directory as directory
import resources.lib.navigation.hub as hub
import resources.lib.navigation.player as player
import resources.lib.navigation.actions as actions
import resources.lib.navigation.library as library

from resources.lib.api.exceptions import (NotLoggedInError, MissingCredentialsError)

NAV_HANDLERS = {
    g.MODE_DIRECTORY: directory.DirectoryBuilder,
    g.MODE_ACTION: actions.AddonActionExecutor,
    g.MODE_LIBRARY: library.LibraryActionExecutor,
    g.MODE_HUB: hub.HubBrowser
}


def lazy_login(func):
    """
    Decorator to ensure that a valid login is present when calling a method
    """
    # pylint: disable=protected-access, missing-docstring
    @wraps(func)
    def lazy_login_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except NotLoggedInError:
            common.debug('Tried to perform an action without being logged in')
            try:
                api.login()
                common.debug('Now that we\'re logged in, let\'s try again')
                return func(*args, **kwargs)
            except MissingCredentialsError:
                # Aborted from user or left an empty field
                xbmcplugin.endOfDirectory(handle=g.PLUGIN_HANDLE,
                                          succeeded=False)
    return lazy_login_wrapper


@lazy_login
def route(pathitems):
    """Route to the appropriate handler"""
    common.debug('Routing navigation request')
    root_handler = pathitems[0] if pathitems else g.MODE_DIRECTORY
    if root_handler == g.MODE_PLAY:
        player.play(pathitems=pathitems[1:])
    elif root_handler == 'extrafanart':
        common.debug('Ignoring extrafanart invocation')
        xbmcplugin.endOfDirectory(handle=g.PLUGIN_HANDLE, succeeded=False)
    elif root_handler not in NAV_HANDLERS:
        raise nav.InvalidPathError(
            'No root handler for path {}'.format('/'.join(pathitems)))
    else:
        nav.execute(NAV_HANDLERS[root_handler], pathitems[1:],
                    g.REQUEST_PARAMS)


def check_valid_credentials():
    """Check that credentials are valid otherwise request user credentials"""
    # This function check only if credentials exist, instead lazy_login
    # only works in conjunction with nfsession and also performs other checks
    if not common.check_credentials():
        try:
            if not api.login():
                # Wrong login try again
                return check_valid_credentials()
        except MissingCredentialsError:
            # Aborted from user or left an empty field
            return False
    return True


if __name__ == '__main__':
    # pylint: disable=broad-except
    # Initialize variables in common module scope
    # (necessary when reusing language invoker)
    common.info('Started (Version {})'.format(g.VERSION))
    common.info('URL is {}'.format(g.URL))
    success = False

    try:
        upgrade_ctrl.check_addon_upgrade()
        g.initial_addon_configuration()
        if check_valid_credentials():
            route(filter(None, g.PATH.split('/')))
            success = True
    except common.BackendNotReady:
        ui.show_backend_not_ready()
    except Exception as exc:
        import traceback
        common.error(traceback.format_exc())
        ui.show_addon_error_info(exc)

    if not success:
        xbmcplugin.endOfDirectory(g.PLUGIN_HANDLE, succeeded=success)

    g.CACHE.commit()
    common.log_time_trace()
