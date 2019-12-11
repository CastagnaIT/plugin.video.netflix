# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Functions for starting the service

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import threading

# Global cache must not be used within these modules, because stale values may
# be used and cause inconsistencies!
from resources.lib.globals import g
from resources.lib.common import (info, error, select_port, get_local_string)
from resources.lib.upgrade_controller import check_service_upgrade


try:  # Python 2
    unicode
except NameError:  # Python 3
    unicode = str  # pylint: disable=redefined-builtin


class NetflixService(object):
    """
    Netflix addon service
    """
    from resources.lib.services.msl.http_server import MSLTCPServer
    from resources.lib.services.nfsession.http_server import NetflixTCPServer
    SERVERS = [
        {
            'name': 'MSL',
            'class': MSLTCPServer,
            'instance': None,
            'thread': None},
        {
            'name': 'NS',
            'class': NetflixTCPServer,
            'instance': None,
            'thread': None},
    ]

    def __init__(self):
        for server in self.SERVERS:
            self.init_server(server)
        self.controller = None
        self.library_updater = None
        self.settings_monitor = None

    def init_server(self, server):
        server['class'].allow_reuse_address = True
        server['instance'] = server['class'](
            ('127.0.0.1', select_port(server['name'])))
        server['thread'] = threading.Thread(
            target=server['instance'].serve_forever)

    def start_services(self):
        """
        Start the background services
        """
        from resources.lib.services.playback.controller import PlaybackController
        from resources.lib.services.library_updater import LibraryUpdateService
        from resources.lib.services.settings_monitor import SettingsMonitor
        for server in self.SERVERS:
            server['instance'].server_activate()
            server['instance'].timeout = 1
            server['thread'].start()
            info('[{}] Thread started'.format(server['name']))
        self.controller = PlaybackController()
        self.library_updater = LibraryUpdateService()
        self.settings_monitor = SettingsMonitor()
        # Mark the service as active
        from xbmcgui import Window
        window_cls = Window(10000)
        window_cls.setProperty('nf_service_status', 'running')
        if not g.ADDON.getSettingBool('disable_startup_notification'):
            from resources.lib.kodi.ui import show_notification
            show_notification(get_local_string(30110))

    def shutdown(self):
        """
        Stop the background services
        """
        from xbmcgui import Window
        window_cls = Window(10000)
        window_cls.setProperty('nf_service_status', 'stopped')
        for server in self.SERVERS:
            server['instance'].server_close()
            server['instance'].shutdown()
            server['instance'] = None
            server['thread'].join()
            server['thread'] = None
        info('Stopped MSL Service')

    def run(self):
        """Main loop. Runs until xbmc.Monitor requests abort"""
        # pylint: disable=broad-except
        try:
            self.start_services()
        except Exception as exc:
            from xbmcgui import Window
            window_cls = Window(10000)
            window_cls.setProperty('nf_service_status', 'stopped')
            import traceback
            from resources.lib.kodi.ui import show_addon_error_info
            error(traceback.format_exc())
            show_addon_error_info(exc)
            return

        while not self.controller.abortRequested():
            if self._tick_and_wait_for_abort():
                break
        self.shutdown()

    def _tick_and_wait_for_abort(self):
        try:
            self.controller.on_playback_tick()
            self.library_updater.on_tick()
        except Exception as exc:  # pylint: disable=broad-except
            import traceback
            from resources.lib.kodi.ui import show_notification
            error(traceback.format_exc())
            show_notification(': '.join((exc.__class__.__name__, unicode(exc))))
        return self.controller.waitForAbort(1)


def run(argv):
    # Initialize globals right away to avoid stale values from the last addon invocation.
    # Otherwise Kodi's reuseLanguageInvoker will cause some really quirky behavior!
    # PR: https://github.com/xbmc/xbmc/pull/13814
    g.init_globals(argv)
    check_service_upgrade()
    NetflixService().run()
