# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Functions for starting the addon

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from functools import wraps

from xbmc import getCondVisibility, Monitor
from xbmcgui import Window

from resources.lib.globals import g
from resources.lib.common import (info, debug, warn, error, check_credentials, BackendNotReady,
                                  log_time_trace, reset_log_level_global_var,
                                  get_current_kodi_profile_name)
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


def _skin_widget_call(window_cls, prop_nf_service_status):
    """
    Workaround to intercept calls made by the Skin Widgets currently in use.
    Currently, the Skin widgets associated with add-ons are executed at Kodi startup immediately
    without respecting any services needed by the add-ons. This is causing different
    kinds of problems like widgets not loaded, add-on warning message, etc...
    this loop freeze the add-on instance until the service is ready.
    """
    # Note to "Window.IsMedia":
    # All widgets will be either on Home or in a Custom Window, so "Window.IsMedia" will be false
    # When the user is browsing the plugin, Window.IsMedia will be true because video add-ons open
    # in MyVideoNav.xml (which is a Media window)
    # This is not a safe solution, because DEPENDS ON WHICH WINDOW IS OPEN,
    # for example it can fail if you open add-on video browser while widget is still loading.
    # Needed a proper solution by script.skinshortcuts / script.skin.helper.service, and forks
    limit_sec = 10
    if not getCondVisibility("Window.IsMedia"):
        monitor = Monitor()
        sec_elapsed = 0
        while not window_cls.getProperty(prop_nf_service_status) == 'running':
            if sec_elapsed >= limit_sec or monitor.abortRequested() or monitor.waitForAbort(0.5):
                break
            sec_elapsed += 0.5
        debug('Skin widget workaround enabled - time elapsed: {}', sec_elapsed)
        return True
    return False


def _get_nav_handler(root_handler):
    nav_handler = None
    if root_handler == g.MODE_DIRECTORY:
        from resources.lib.navigation.directory import DirectoryBuilder
        nav_handler = DirectoryBuilder
    if root_handler == g.MODE_ACTION:
        from resources.lib.navigation.actions import AddonActionExecutor
        nav_handler = AddonActionExecutor
    if root_handler == g.MODE_LIBRARY:
        from resources.lib.navigation.library import LibraryActionExecutor
        nav_handler = LibraryActionExecutor
    if root_handler == g.MODE_HUB:
        from resources.lib.navigation.hub import HubBrowser
        nav_handler = HubBrowser
    return nav_handler


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


def run(argv):
    # pylint: disable=broad-except,ungrouped-imports
    # Initialize globals right away to avoid stale values from the last addon invocation.
    # Otherwise Kodi's reuseLanguageInvoker will cause some really quirky behavior!
    # PR: https://github.com/xbmc/xbmc/pull/13814
    g.init_globals(argv)

    reset_log_level_global_var()
    info('Started (Version {})'.format(g.VERSION))
    info('URL is {}'.format(g.URL))
    success = True

    window_cls = Window(10000)  # Kodi home window
    # If you use multiple Kodi profiles you need to distinguish the property of current profile
    prop_nf_service_status = g.py2_encode('nf_service_status_' + get_current_kodi_profile_name())
    is_widget_skin_call = _skin_widget_call(window_cls, prop_nf_service_status)

    if window_cls.getProperty(prop_nf_service_status) != 'running':
        if not is_widget_skin_call:
            from resources.lib.kodi.ui import show_backend_not_ready
            show_backend_not_ready()
        success = False

    if success:
        try:
            if _check_valid_credentials():
                if g.IS_ADDON_FIRSTRUN:
                    check_addon_upgrade()
                g.initial_addon_configuration()
                route([part for part in g.PATH.split('/') if part])
            else:
                success = False
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
