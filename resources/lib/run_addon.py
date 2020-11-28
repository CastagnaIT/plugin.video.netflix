# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Functions for starting the addon

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from functools import wraps
from future.utils import raise_from

from xbmc import getCondVisibility, Monitor, getInfoLabel

from resources.lib.common.exceptions import (HttpError401, InputStreamHelperError, MbrStatusNeverMemberError,
                                             MbrStatusFormerMemberError, MissingCredentialsError, LoginError,
                                             NotLoggedInError, InvalidPathError, BackendNotReady, HttpErrorTimeout)
from resources.lib.common import check_credentials, get_local_string, WndHomeProps
from resources.lib.globals import G
from resources.lib.upgrade_controller import check_addon_upgrade
from resources.lib.utils.logging import LOG


def catch_exceptions_decorator(func):
    """Decorator that catch exceptions"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # pylint: disable=broad-except, ungrouped-imports
        success = False
        try:
            func(*args, **kwargs)
            success = True
        except BackendNotReady as exc_bnr:
            from resources.lib.kodi.ui import show_backend_not_ready
            show_backend_not_ready(G.py2_decode(str(exc_bnr), 'latin-1'))
        except InputStreamHelperError as exc:
            from resources.lib.kodi.ui import show_ok_dialog
            show_ok_dialog('InputStream Helper Add-on error',
                           ('The operation has been cancelled.[CR]'
                            'InputStream Helper has generated an internal error:[CR]{}[CR][CR]'
                            'Please report it to InputStream Helper github.'.format(exc)))
        except (HttpError401, HttpErrorTimeout) as exc:
            # HttpError401: This is a generic error, can happen when the http request for some reason has failed.
            # Known causes:
            # - Possible change of data format or wrong data in the http request (also in headers/params)
            # - Some current nf session data are not more valid (authURL/cookies/...)
            # HttpErrorTimeout: This error is raised by Requests ReadTimeout error, unknown causes
            from resources.lib.kodi.ui import show_ok_dialog
            show_ok_dialog(get_local_string(30105),
                           ('There was a communication problem with Netflix.[CR]'
                            'You can try the operation again or exit.[CR]'
                            '(Error code: {})').format(exc.__class__.__name__))
        except (MbrStatusNeverMemberError, MbrStatusFormerMemberError):
            from resources.lib.kodi.ui import show_error_info
            show_error_info(get_local_string(30008), get_local_string(30180), False, True)
        except Exception as exc:
            import traceback
            from resources.lib.kodi.ui import show_addon_error_info
            LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))
            show_addon_error_info(exc)
        finally:
            if not success:
                from xbmcplugin import endOfDirectory
                endOfDirectory(handle=G.PLUGIN_HANDLE, succeeded=False)
    return wrapper


def _check_valid_credentials():
    """Check that credentials are valid otherwise request user credentials"""
    if not check_credentials():
        try:
            from resources.lib.utils.api_requests import login
            if not login():
                # Wrong login try again
                return _check_valid_credentials()
        except MissingCredentialsError:
            # Aborted from user or left an empty field
            return False
    return True


def lazy_login(func):
    """
    Decorator to ensure that a valid login is present when calling a method
    """
    @wraps(func)
    def lazy_login_wrapper(*args, **kwargs):
        if _check_valid_credentials():
            try:
                return func(*args, **kwargs)
            except NotLoggedInError:
                # Exception raised by nfsession: "login" / "assert_logged_in" / "website_extract_session_data"
                LOG.debug('Tried to perform an action without being logged in')
                try:
                    from resources.lib.utils.api_requests import login
                    if login(ask_credentials=not check_credentials()):
                        LOG.debug('Account logged in, try executing again {}', func.__name__)
                        return func(*args, **kwargs)
                except MissingCredentialsError:
                    # Cancelled from user or left an empty field
                    pass
                except LoginError as exc:
                    # Login not valid
                    from resources.lib.kodi.ui import show_ok_dialog
                    show_ok_dialog(get_local_string(30008), str(exc))
        return False
    return lazy_login_wrapper


@lazy_login
def route(pathitems):
    """Route to the appropriate handler"""
    LOG.debug('Routing navigation request')
    if pathitems:
        if 'extrafanart' in pathitems:
            LOG.warn('Route: ignoring extrafanart invocation')
            return False
        root_handler = pathitems[0]
    else:
        root_handler = G.MODE_DIRECTORY
    if root_handler == G.MODE_PLAY:
        from resources.lib.navigation.player import play
        play(videoid=pathitems[1:])
    elif root_handler == G.MODE_PLAY_STRM:
        from resources.lib.navigation.player import play_strm
        play_strm(videoid=pathitems[1:])
    else:
        nav_handler = _get_nav_handler(root_handler, pathitems)
        _execute(nav_handler, pathitems[1:], G.REQUEST_PARAMS, root_handler)
    return True


def _get_nav_handler(root_handler, pathitems):
    nav_handler = None
    if root_handler == G.MODE_DIRECTORY:
        from resources.lib.navigation.directory import Directory
        nav_handler = Directory
    elif root_handler == G.MODE_ACTION:
        from resources.lib.navigation.actions import AddonActionExecutor
        nav_handler = AddonActionExecutor
    elif root_handler == G.MODE_LIBRARY:
        from resources.lib.navigation.library import LibraryActionExecutor
        nav_handler = LibraryActionExecutor
    elif root_handler == G.MODE_KEYMAPS:
        from resources.lib.navigation.keymaps import KeymapsActionExecutor
        nav_handler = KeymapsActionExecutor
    if not nav_handler:
        raise InvalidPathError('No root handler for path {}'.format('/'.join(pathitems)))
    return nav_handler


def _execute(executor_type, pathitems, params, root_handler):
    """Execute an action as specified by the path"""
    try:
        executor = executor_type(params).__getattribute__(pathitems[0] if pathitems else 'root')
        LOG.debug('Invoking action: {}', executor.__name__)
        executor(pathitems=pathitems)
        if root_handler == G.MODE_DIRECTORY and not G.IS_ADDON_EXTERNAL_CALL:
            # Save the method name of current loaded directory
            WndHomeProps[WndHomeProps.CURRENT_DIRECTORY] = executor.__name__
            WndHomeProps[WndHomeProps.IS_CONTAINER_REFRESHED] = None
    except AttributeError as exc:
        raise_from(InvalidPathError('Unknown action {}'.format('/'.join(pathitems))), exc)


def _get_service_status():
    from json import loads
    try:
        status = WndHomeProps[WndHomeProps.SERVICE_STATUS]
        return loads(status) if status else {}
    except Exception:  # pylint: disable=broad-except
        return {}


def _check_addon_external_call():
    """Check system to verify if the calls to the add-on are originated externally"""
    # The calls that are made from outside do not respect and do not check whether the services required
    # for the add-on are actually working and operational, causing problems with the execution of the frontend.

    # A clear example are the Skin widgets, that are executed at Kodi startup immediately and this is cause of different
    # kinds of problems like widgets not loaded, add-on warning message, etc...

    # Cases where it can happen:
    # - Calls made by the Skin Widgets, Scripts, Kodi library
    # - Calls made by others Kodi windows (like file browser)
    # - Calls made by other add-ons

    # To try to solve the problem, when the service is not ready a loop will be started to freeze the add-on instance
    # until the service will be ready.

    is_other_plugin_name = getInfoLabel('Container.PluginName') != G.ADDON.getAddonInfo('id')
    limit_sec = 10

    # Note to Kodi boolean condition "Window.IsMedia":
    # All widgets will be either on Home or in a Custom Window, so "Window.IsMedia" will be false
    # When the user is browsing the plugin, Window.IsMedia will be true because video add-ons open
    # in MyVideoNav.xml (which is a Media window)
    # This is not a safe solution, because DEPENDS ON WHICH WINDOW IS OPEN,
    # for example it can fail if you open add-on video browser while widget is still loading.
    # Needed a proper solution by script.skinshortcuts / script.skin.helper.service, and forks
    if is_other_plugin_name or not getCondVisibility("Window.IsMedia"):
        monitor = Monitor()
        sec_elapsed = 0
        while not _get_service_status().get('status') == 'running':
            if sec_elapsed >= limit_sec or monitor.abortRequested() or monitor.waitForAbort(0.5):
                break
            sec_elapsed += 0.5
        LOG.debug('Add-on was initiated by an external call - workaround enabled time elapsed {}s', sec_elapsed)
        G.IS_ADDON_EXTERNAL_CALL = True
        return True
    return False


@catch_exceptions_decorator
def run(argv):
    # Initialize globals right away to avoid stale values from the last addon invocation.
    # Otherwise Kodi's reuseLanguageInvoker will cause some really quirky behavior!
    # PR: https://github.com/xbmc/xbmc/pull/13814
    G.init_globals(argv)

    LOG.info('Started (Version {})'.format(G.VERSION_RAW))
    LOG.info('URL is {}'.format(G.URL))
    success = True

    is_external_call = _check_addon_external_call()
    service_status = _get_service_status()

    if service_status.get('status') != 'running':
        if not is_external_call:
            if service_status.get('status') == 'error':
                # The services are not started due to an error exception
                from resources.lib.kodi.ui import show_error_info
                show_error_info(get_local_string(30105), get_local_string(30240).format(service_status.get('message')),
                                False, False)
            else:
                # The services are not started yet
                from resources.lib.kodi.ui import show_backend_not_ready
                show_backend_not_ready()
        success = False
    if success:
        cancel_playback = False
        pathitems = [part for part in G.REQUEST_PATH.split('/') if part]
        if G.IS_ADDON_FIRSTRUN:
            is_first_run_install, cancel_playback = check_addon_upgrade()
            if is_first_run_install:
                from resources.lib.config_wizard import run_addon_configuration
                run_addon_configuration()
        if cancel_playback and G.MODE_PLAY in pathitems[:1]:
            # Temporary for migration library STRM to new format. todo: to be removed in future releases
            # When a user do the add-on upgrade, the first time that the add-on will be opened will be executed
            # the library migration. But if a user instead to open the add-on, try to play a video from Kodi
            # library, Kodi will open the old STRM file because the migration is executed after.
            success = False
        else:
            success = route(pathitems)
    if not success:
        from xbmcplugin import endOfDirectory
        endOfDirectory(handle=G.PLUGIN_HANDLE, succeeded=False)
    LOG.log_time_trace()
