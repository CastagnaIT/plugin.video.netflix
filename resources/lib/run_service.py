# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Functions for starting the service

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import threading
from socket import gaierror

from xbmcgui import Window

# Global cache must not be used within these modules, because stale values may
# be used and cause inconsistencies!
from resources.lib.common import (info, error, select_port, get_local_string,
                                  get_current_kodi_profile_name)
from resources.lib.globals import g
from resources.lib.upgrade_controller import check_service_upgrade

try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


class NetflixService(object):
    """
    Netflix addon service
    """
    SERVERS = []
    HOST_ADDRESS = '127.0.0.1'

    def __init__(self):
        self.window_cls = Window(10000)  # Kodi home window
        # If you use multiple Kodi profiles you need to distinguish the property of current profile
        self.prop_nf_service_status = g.py2_encode('nf_service_status_' + get_current_kodi_profile_name())
        self.controller = None
        self.library_updater = None
        self.settings_monitor = None

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
            error('Background services do not start due to the following error')
            import traceback
            error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            if isinstance(exc, gaierror):
                message = ('Something is wrong in your network localhost configuration.\r\n'
                           'It is possible that the hostname {} can not be resolved.').format(self.HOST_ADDRESS)
            elif isinstance(exc, ImportError):
                message = ('In your system is missing some required library to run Netflix.\r\n'
                           'Read how to install the add-on in the GitHub Readme.\r\n'
                           'Error details: {}'.format(exc))
            else:
                message = unicode(exc)
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
        from resources.lib.services.settings_monitor import SettingsMonitor
        for server in self.SERVERS:
            server['instance'].server_activate()
            server['instance'].timeout = 1
            server['thread'].start()
            info('[{}] Thread started'.format(server['name']))
        self.controller = ActionController()
        self.library_updater = LibraryUpdateService()
        self.settings_monitor = SettingsMonitor()
        # Mark the service as active
        self._set_service_status('running')
        if not g.ADDON.getSettingBool('disable_startup_notification'):
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
        info('Stopped MSL Service')

    def run(self):
        """Main loop. Runs until xbmc.Monitor requests abort"""
        try:
            self.start_services()
        except Exception as exc:  # pylint: disable=broad-except
            self._set_service_status('stopped')
            import traceback
            from resources.lib.kodi.ui import show_addon_error_info
            error(g.py2_decode(traceback.format_exc(), 'latin-1'))
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
            g.CACHE_MANAGEMENT.on_service_tick()
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            from resources.lib.kodi.ui import show_notification
            error(g.py2_decode(traceback.format_exc(), 'latin-1'))
            show_notification(': '.join((exc.__class__.__name__, unicode(exc))))
        return self.controller.waitForAbort(1)

    def _set_service_status(self, status, message=None):
        """Save the service status to a Kodi property"""
        from json import dumps
        status = {'status': status, 'message': message}
        self.window_cls.setProperty(self.prop_nf_service_status, dumps(status))


def run(argv):
    # Initialize globals right away to avoid stale values from the last addon invocation.
    # Otherwise Kodi's reuseLanguageInvoker will cause some really quirky behavior!
    # PR: https://github.com/xbmc/xbmc/pull/13814
    g.init_globals(argv)
    check_service_upgrade()
    netflix_service = NetflixService()
    if netflix_service.init_servers():
        netflix_service.run()
