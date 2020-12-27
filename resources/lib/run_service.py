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
    """
    Netflix addon service
    """
    SERVERS = []
    HOST_ADDRESS = '127.0.0.1'

    def __init__(self):
        self.controller = None
        self.library_updater = None

    def init_servers(self):
        """Initialize the http servers"""
        try:
            # Import modules here to intercept possible missing libraries on linux systems
            from resources.lib.services.msl.http_server import MSLTCPServer
            from resources.lib.services.nfsession.http_server import NetflixTCPServer
            from resources.lib.services.cache.http_server import CacheTCPServer
            # Do not change the init order of the servers,
            # MSLTCPServer must always be initialized first to get the DRM info
            self.SERVERS = [
                {
                    'name': 'MSL',
                    'class': MSLTCPServer,
                    'instance': None,
                    'thread': None
                }, {
                    'name': 'NS',
                    'class': NetflixTCPServer,
                    'instance': None,
                    'thread': None
                }, {
                    'name': 'CACHE',
                    'class': CacheTCPServer,
                    'instance': None,
                    'thread': None
                }
            ]

            for server in self.SERVERS:
                self._init_server(server)
            return True
        except Exception as exc:  # pylint: disable=broad-except
            LOG.error('Background services do not start due to the following error')
            import traceback
            LOG.error(traceback.format_exc())
            if isinstance(exc, gaierror):
                message = ('Something is wrong in your network localhost configuration.\r\n'
                           'It is possible that the hostname {} can not be resolved.').format(self.HOST_ADDRESS)
            elif isinstance(exc, ImportError):
                message = ('In your system is missing some required library to run Netflix.\r\n'
                           'Read how to install the add-on in the GitHub Readme.\r\n'
                           'Error details: {}'.format(exc))
            else:
                message = str(exc)
            self._set_service_status('error', message)
        return False

    def _init_server(self, server):
        server['class'].allow_reuse_address = True
        server['instance'] = server['class'](
            (self.HOST_ADDRESS, select_port(server['name']))
        )
        server['thread'] = threading.Thread(target=server['instance'].serve_forever)

    def start_services(self):
        """
        Start the background services
        """
        from resources.lib.services.playback.action_controller import ActionController
        from resources.lib.services.library_updater import LibraryUpdateService
        for server in self.SERVERS:
            server['instance'].server_activate()
            server['instance'].timeout = 1
            server['thread'].start()
            LOG.info('[{}] Thread started'.format(server['name']))
        self.controller = ActionController()
        self.library_updater = LibraryUpdateService()
        # We reset the value in case of any eventuality (add-on disabled, update, etc)
        WndHomeProps[WndHomeProps.CURRENT_DIRECTORY] = None
        # Mark the service as active
        self._set_service_status('running')
        if not G.ADDON.getSettingBool('disable_startup_notification'):
            from resources.lib.kodi.ui import show_notification
            show_notification(get_local_string(30110))

    def shutdown(self):
        """
        Stop the background services
        """
        self._set_service_status('stopped')
        for server in self.SERVERS:
            server['instance'].shutdown()
            server['instance'].server_close()
            server['instance'] = None
            server['thread'].join()
            server['thread'] = None
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

        while not self.controller.abortRequested():
            if self._tick_and_wait_for_abort():
                break
        self.shutdown()

    def _tick_and_wait_for_abort(self):
        try:
            self.controller.on_service_tick()
            self.library_updater.on_service_tick()
            G.CACHE_MANAGEMENT.on_service_tick()
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            from resources.lib.kodi.ui import show_notification
            LOG.error(traceback.format_exc())
            show_notification(': '.join((exc.__class__.__name__, str(exc))))
        return self.controller.waitForAbort(1)

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
