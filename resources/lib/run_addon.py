# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=wrong-import-position
"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import absolute_import, division, unicode_literals

import sys
from functools import wraps
from xbmcgui import Window

# Import and initialize globals right away to avoid stale values from the last
# addon invocation. Otherwise Kodi's reuseLanguageInvoker will cause some
# really quirky behavior!
# PR: https://github.com/xbmc/xbmc/pull/13814
from resources.lib.globals import g
g.init_globals(sys.argv)

from resources.lib.common import (info, debug, warn, error, check_credentials, BackendNotReady,
                                  log_time_trace, reset_log_level_global_var)
from resources.lib.upgrade_controller import check_addon_upgrade


def lazy_login(func):
    """
    Decorator to ensure that a valid login is present when calling a method
    """
    # pylint: missing-docstring
    @wraps(func)
    def lazy_login_wrapper(*args, **kwargs):
        from resources.lib.api.exceptions import (NotLoggedInError, MissingCredentialsError)
        try:
            return func(*args, **kwargs)
        except NotLoggedInError:
            debug('Tried to perform an action without being logged in')
            try:
                from resources.lib.api.shakti import login
                if not login(ask_credentials=not check_credentials()):
                    _handle_endofdirectory()
                    raise MissingCredentialsError
                debug('Now that we\'re logged in, let\'s try again')
                return func(*args, **kwargs)
            except MissingCredentialsError:
                # Aborted from user or left an empty field
                _handle_endofdirectory()
                raise
    return lazy_login_wrapper


@lazy_login
def route(pathitems):
    """Route to the appropriate handler"""
    debug('Routing navigation request')
    root_handler = pathitems[0] if pathitems else g.MODE_DIRECTORY
    if root_handler == g.MODE_PLAY:
        from resources.lib.navigation.player import play
        play(videoid=pathitems[1:])
        return
    if root_handler == 'extrafanart':
        warn('Route: ignoring extrafanart invocation')
        _handle_endofdirectory()
        return
    nav_handler = _get_nav_handler(root_handler)
    if not nav_handler:
        from resources.lib.navigation import InvalidPathError
        raise InvalidPathError('No root handler for path {}'.format('/'.join(pathitems)))
    from resources.lib.navigation import execute
    execute(_get_nav_handler(root_handler), pathitems[1:], g.REQUEST_PARAMS)


def _get_nav_handler(root_handler):
    if root_handler == g.MODE_DIRECTORY:
        from resources.lib.navigation.directory import DirectoryBuilder
        return DirectoryBuilder
    if root_handler == g.MODE_ACTION:
        from resources.lib.navigation.actions import AddonActionExecutor
        return AddonActionExecutor
    if root_handler == g.MODE_LIBRARY:
        from resources.lib.navigation.library import LibraryActionExecutor
        return LibraryActionExecutor
    if root_handler == g.MODE_HUB:
        from resources.lib.navigation.hub import HubBrowser
        return HubBrowser
    return None


def _check_valid_credentials():
    """Check that credentials are valid otherwise request user credentials"""
    # This function check only if credentials exist, instead lazy_login
    # only works in conjunction with nfsession and also performs other checks
    if not check_credentials():
        from resources.lib.api.exceptions import MissingCredentialsError
        try:
            from resources.lib.api.shakti import login
            if not login():
                # Wrong login try again
                return _check_valid_credentials()
        except MissingCredentialsError:
            # Aborted from user or left an empty field
            return False
    return True


def _handle_endofdirectory(succeeded=False):
    from xbmcplugin import endOfDirectory
    endOfDirectory(handle=g.PLUGIN_HANDLE, succeeded=succeeded)


def run():
    # pylint: disable=broad-except,ungrouped-imports
    # Initialize variables in common module scope
    # (necessary when reusing language invoker)
    reset_log_level_global_var()
    info('Started (Version {})'.format(g.VERSION))
    info('URL is {}'.format(g.URL))
    success = True

    window_cls = Window(10000)
    if not bool(window_cls.getProperty('is_service_running')):
        from resources.lib.kodi.ui import show_backend_not_ready
        show_backend_not_ready()
        success = False

    if success:
        try:
            if _check_valid_credentials():
                check_addon_upgrade()
                g.initial_addon_configuration()
                route([part for part in g.PATH.split('/') if part])
        except BackendNotReady:
            from resources.lib.kodi.ui import show_backend_not_ready
            show_backend_not_ready()
            success = False
        except Exception as exc:
            import traceback
            from resources.lib.kodi.ui import show_addon_error_info
            error(traceback.format_exc())
            show_addon_error_info(exc)
            success = False

    if not success:
        _handle_endofdirectory()

    g.CACHE.commit()
    log_time_trace()
