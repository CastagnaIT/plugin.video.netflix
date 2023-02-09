# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Functions for starting the addon

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from functools import wraps

from xbmc import getCondVisibility, Monitor, getInfoLabel

from resources.lib.common.exceptions import (HttpError401, InputStreamHelperError, MbrStatusNeverMemberError,
                                             MbrStatusFormerMemberError, MissingCredentialsError, LoginError,
                                             NotLoggedInError, InvalidPathError, BackendNotReady, ErrorMsgNoReport)
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
            show_backend_not_ready(str(exc_bnr))
        except InputStreamHelperError as exc:
            from resources.lib.kodi.ui import show_ok_dialog
            show_ok_dialog('InputStream Helper Add-on error',
                           ('The operation has been cancelled.[CR]'
                            f'InputStream Helper has generated an internal error:[CR]{exc}[CR][CR]'
                            'Please report it to InputStream Helper github.'))
        except HttpError401 as exc:
            # This is a generic error, can happen when the http request for some reason has failed.
            # Known causes:
            # - Possible change of data format or wrong data in the http request (also in headers/params)
            # - Some current nf session data are not more valid (authURL/cookies/...)
            from resources.lib.kodi.ui import show_ok_dialog
            show_ok_dialog(get_local_string(30105),
                           ('There was a communication problem with Netflix.[CR]'
                            'You can try the operation again or exit.[CR]'
                            f'(Error code: {exc.__class__.__name__})'))
        except (MbrStatusNeverMemberError, MbrStatusFormerMemberError):
            from resources.lib.kodi.ui import show_error_info
            show_error_info(get_local_string(30008), get_local_string(30180), False, True)
        except ErrorMsgNoReport as exc:
            from resources.lib.kodi.ui import show_ok_dialog
            show_ok_dialog(get_local_string(30105), str(exc))
        except Exception as exc:
            import traceback
            from resources.lib.kodi.ui import show_addon_error_info
            LOG.error(traceback.format_exc())
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
        if G.REQUEST_PARAMS.get('ignore_login') or _check_valid_credentials():
            try:
                return func(*args, **kwargs)
            except NotLoggedInError:
                # Exception raised by nfsession:
                #   "login" / "assert_logged_in" / "website_extract_session_data" / _request from http_requests.py
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
    else:
        raise InvalidPathError(f'No root handler for path {"/".join(pathitems)}')
    return nav_handler


def _execute(executor_type, pathitems, params, root_handler):
    """Execute an action as specified by the path"""
    try:
        executor = getattr(executor_type(params), pathitems[0] if pathitems else 'root')
    except AttributeError as exc:
        raise InvalidPathError(f'Unknown action {"/".join(pathitems)}') from exc
    LOG.debug('Invoking action: {}', executor.__name__)
    executor(pathitems=pathitems)
    if root_handler == G.MODE_DIRECTORY and not G.IS_ADDON_EXTERNAL_CALL:
        # Save the method name of current loaded directory and his menu item id
        WndHomeProps[WndHomeProps.CURRENT_DIRECTORY] = executor.__name__
        WndHomeProps[WndHomeProps.CURRENT_DIRECTORY_MENU_ID] = pathitems[1] if len(pathitems) > 1 else ''
        WndHomeProps[WndHomeProps.IS_CONTAINER_REFRESHED] = None


def _get_service_status():
    from json import loads
    try:
        status = WndHomeProps[WndHomeProps.SERVICE_STATUS]
        if status:
            return loads(status)
    except Exception:  # pylint: disable=broad-except
        LOG.warn('Cannot read SERVICE_STATUS property from Kodi home window')
    return {'status': G.SERVICE_STATUS_STARTUP}


def _verify_external_call():
    """Verify if the add-on call is coming from external parties."""
    # What follows is not a 100% safe method, but it is the best that can be done at the moment
    # Examples of calls made by external parties:
    # - Skin Widgets, Scripts, Kodi library, Keyboard shortcut
    # - Kodi windows like file browser
    # - Third party add-ons
    is_other_plugin_name = getInfoLabel('Container.PluginName') != G.ADDON.getAddonInfo('id')
    # Note to Kodi boolean condition "Window.IsMedia":
    # All widgets will be either on Home or in a Custom Window, so "Window.IsMedia" will be false
    # When the user is browsing the plugin, Window.IsMedia will be true because video add-ons open
    # in MyVideoNav.xml (which is a Media window)
    # This is not a safe solution, because DEPENDS ON WHICH WINDOW IS OPEN,
    # for example it can fail if you open add-on video browser while widget is still loading.
    # Needed a proper solution by script.skinshortcuts / script.skin.helper.service, and forks
    if is_other_plugin_name or not getCondVisibility('Window.IsMedia'):
        G.IS_ADDON_EXTERNAL_CALL = True


def _check_service():
    """
    Check whether the add-on service is up, otherwise wait for start-up.

    :returns: True if service is running, otherwise False
    """
    # The calls to the add-on are made by ignoring the add-on service status,
    # so we must check the service and wait right here until it is ready
    status = _get_service_status()
    if status['status'] == G.SERVICE_STATUS_RUNNING:
        return True
    # Waiting for service start-up
    timeout_secs = 20
    is_progress_hidden = G.IS_ADDON_EXTERNAL_CALL
    from xbmcgui import DialogProgressBG
    dialog = DialogProgressBG()
    if not is_progress_hidden:
        dialog.create('Netflix', get_local_string(30136))
    monitor = Monitor()
    from time import perf_counter
    start = perf_counter()
    while status['status'] == G.SERVICE_STATUS_STARTUP:
        elapsed_time = perf_counter() - start
        if elapsed_time >= timeout_secs or monitor.abortRequested() or monitor.waitForAbort(0.5):
            break
        if not is_progress_hidden:
            dialog.update(percent=int(elapsed_time * 100 / timeout_secs))
        status = _get_service_status()
    if not is_progress_hidden:
        dialog.close()

    if status['status'] == G.SERVICE_STATUS_RUNNING:
        return True

    LOG.warn('The add-on service is not running (service status: {}).', status['status'])
    if not G.IS_ADDON_EXTERNAL_CALL:  # With external calls (e.g. widgets/scripts) we do not have to show GUI messages
        if status['status'] == G.SERVICE_STATUS_ERROR:
            # The services are not started due to an error exception
            from resources.lib.kodi.ui import show_error_info
            show_error_info(get_local_string(30105), get_local_string(30240).format(status.get('message', '--')),
                            False, False)
        elif status['status'] == G.SERVICE_STATUS_UPGRADE:
            from resources.lib.kodi.ui import show_ok_dialog
            show_ok_dialog('Netflix', 'An upgrade of add-on service is in progress, please wait.')
        else:
            from resources.lib.kodi.ui import show_backend_not_ready
            show_backend_not_ready()
    return False


@catch_exceptions_decorator
def run(argv):
    # Initialize globals right away to avoid stale values from the last addon invocation.
    # Otherwise Kodi's reuseLanguageInvoker will cause some really quirky behavior!
    # PR: https://github.com/xbmc/xbmc/pull/13814
    G.init_globals(argv)
    _verify_external_call()

    LOG.info('Started (version {})\nURL: {}\nFrom external call: {}', G.VERSION_RAW, G.URL, G.IS_ADDON_EXTERNAL_CALL)

    success = False
    if _check_service():
        pathitems = [part for part in G.REQUEST_PATH.split('/') if part]
        if G.IS_ADDON_FIRSTRUN:
            is_first_run_install = check_addon_upgrade()
            if is_first_run_install:
                from resources.lib.config_wizard import run_addon_configuration
                run_addon_configuration()
        success = route(pathitems)
    if not success:
        from xbmcplugin import endOfDirectory
        endOfDirectory(handle=G.PLUGIN_HANDLE, succeeded=False)
    LOG.log_time_trace()
