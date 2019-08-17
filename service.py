# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: service
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H
# pylint: disable=wrong-import-position
"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import sys
import threading
import traceback

# Import and initialize globals right away to avoid stale values from the last
# addon invocation. Otherwise Kodi's reuseLanguageInvoker option will cause
# some really quirky behavior!
from resources.lib.globals import g
g.init_globals(sys.argv)

# Global cache must not be used within these modules, because stale values may
# be used and cause inconsistencies!
import resources.lib.common as common
import resources.lib.services as services
import resources.lib.kodi.ui as ui
import resources.lib.upgrade_controller as upgrade_ctrl


class NetflixService(object):
    """
    Netflix addon service
    """
    SERVERS = [
        {
            'name': 'MSL',
            'class': services.MSLTCPServer,
            'instance': None,
            'thread': None},
        {
            'name': 'NS',
            'class': services.NetflixTCPServer,
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
                ('127.0.0.1', common.select_port(server['name'])))
            server['thread'] = threading.Thread(
                target=server['instance'].serve_forever)

    def start_services(self):
        """
        Start the background services
        """
        for server in self.SERVERS:
            server['instance'].server_activate()
            server['instance'].timeout = 1
            server['thread'].start()
            common.info('[{}] Thread started'.format(server['name']))
        self.controller = services.PlaybackController()
        self.library_updater = services.LibraryUpdateService()
        self.settings_monitor = services.SettingsMonitor()
        if not g.ADDON.getSettingBool('disable_startup_notification'):
            ui.show_notification(common.get_local_string(30110))

    def shutdown(self):
        """
        Stop the background services
        """
        for server in self.SERVERS:
            server['instance'].server_close()
            server['instance'].shutdown()
            server['instance'] = None
            server['thread'].join()
            server['thread'] = None
        common.info('Stopped MSL Service')

    def run(self):
        """Main loop. Runs until xbmc.Monitor requests abort"""
        # pylint: disable=broad-except
        try:
            self.start_services()
        except Exception as exc:
            ui.show_addon_error_info(exc)
            return

        while not self.controller.abortRequested():
            if self._tick_and_wait_for_abort():
                break
        self.shutdown()

    def _tick_and_wait_for_abort(self):
        # pylint: disable=broad-except
        try:
            self.controller.on_playback_tick()
            self.library_updater.on_tick()
        except Exception as exc:
            common.error(traceback.format_exc())
            ui.show_notification(': '.join((exc.__class__.__name__,
                                            exc.message)))
        return self.controller.waitForAbort(1)


if __name__ == '__main__':
    upgrade_ctrl.check_service_upgrade()
    NetflixService().run()
