# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Functions for starting the service

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import threading
from socket import gaierror
from resources.lib.common import select_port, get_local_string, WndHomeProps
from resources.lib.globals import G
from resources.lib.upgrade_controller import check_service_upgrade
from resources.lib.utils.logging import LOG


class NetflixService:
    """Netflix addon service"""
    HOST_ADDRESS = '127.0.0.1'

    def __init__(self):
        self.library_updater = None
        self.nf_server_instance = None
        self.nf_server_thread = None

    def init_servers(self):
        """Initialize the HTTP server"""
        try:
            # Import modules here to intercept possible missing libraries on linux systems
            from resources.lib.services.http_server import NFThreadedTCPServer
            self.nf_server_instance = NFThreadedTCPServer((self.HOST_ADDRESS, select_port('NF_SERVER')))
            self.nf_server_instance.allow_reuse_address = True
            self.nf_server_thread = threading.Thread(target=self.nf_server_instance.serve_forever)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            LOG.error('Background services do not start due to the following error')
            import traceback
            LOG.error(traceback.format_exc())
            if isinstance(exc, gaierror):
                message = ('Something is wrong in your network localhost configuration.\r\n'
                           f'It is possible that the hostname {self.HOST_ADDRESS} can not be resolved.')
            elif isinstance(exc, ImportError):
                message = ('In your system is missing some required library to run Netflix.\r\n'
                           'Read how to install the add-on in the GitHub Readme.\r\n'
                           f'Error details: {exc}')
            else:
                message = str(exc)
            self._set_service_status('error', message)
        return False

    def start_services(self):
        """Start the background services"""
        from resources.lib.services.library_updater import LibraryUpdateService

        self.nf_server_instance.server_activate()
        self.nf_server_thread.start()
        LOG.info('[NF_SERVER] Thread started')

        self.library_updater = LibraryUpdateService()
        # We reset the value in case of any eventuality (add-on disabled, update, etc)
        WndHomeProps[WndHomeProps.CURRENT_DIRECTORY] = None
        # Mark the service as active
        self._set_service_status('running')
        if not G.ADDON.getSettingBool('disable_startup_notification'):
            from resources.lib.kodi.ui import show_notification
            show_notification(get_local_string(30110))

    def shutdown(self):
        """Stop the background services"""
        self._set_service_status('stopped')
        self.nf_server_instance.shutdown()
        self.nf_server_instance.server_close()
        self.nf_server_instance = None
        self.nf_server_thread.join()
        self.nf_server_thread = None
        LOG.info('Stopped MSL Service')

    def run(self):
        """Main loop. Runs until xbmc.Monitor requests abort"""
        try:
            self.start_services()
        except Exception as exc:  # pylint: disable=broad-except
            self._set_service_status('stopped')
            import traceback
            from resources.lib.kodi.ui import show_addon_error_info
            LOG.error(traceback.format_exc())
            show_addon_error_info(exc)
            return

        while not G.SETTINGS_MONITOR.abortRequested():
            if self._tick_and_wait_for_abort():
                break
        self.shutdown()

    def _tick_and_wait_for_abort(self):
        try:
            self.library_updater.on_service_tick()
            G.CACHE_MANAGEMENT.on_service_tick()
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            from resources.lib.kodi.ui import show_notification
            LOG.error(traceback.format_exc())
            show_notification(': '.join((exc.__class__.__name__, str(exc))))
        return G.SETTINGS_MONITOR.waitForAbort(1)

    def _set_service_status(self, status, message=None):
        """Save the service status to a Kodi property"""
        from json import dumps
        status = {'status': status, 'message': message}
        WndHomeProps[WndHomeProps.SERVICE_STATUS] = dumps(status)


def run(argv):
    # Initialize globals right away to avoid stale values from the last addon invocation.
    # Otherwise Kodi's reuseLanguageInvoker will cause some really quirky behavior!
    # PR: https://github.com/xbmc/xbmc/pull/13814
    G.init_globals(argv)
    check_service_upgrade()
    netflix_service = NetflixService()
    if netflix_service.init_servers():
        netflix_service.run()
