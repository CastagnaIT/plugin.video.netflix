# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: service
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import sys
import threading

import xbmc

import resources.lib.common as common
import resources.lib.services as services
from resources.lib.services.nfsession import NetflixSession

class NetflixService(object):
    """
    Netflix addon service
    """
    def __init__(self):
        services.MSLTCPServer.allow_reuse_address = True
        self.msl_server = services.MSLTCPServer(
            ('127.0.0.1', common.select_port()))
        self.msl_thread = threading.Thread(
            target=self.msl_server.serve_forever)
        self.session = None
        self.controller = None
        self.library_updater = None

    def start_services(self):
        """
        Start the background services
        """
        self.session = NetflixSession()
        self.msl_server.server_activate()
        self.msl_server.timeout = 1
        self.msl_thread.start()
        common.info('[MSL] Thread started')
        self.controller = services.PlaybackController()
        self.library_updater = services.LibraryUpdateService()

    def shutdown(self):
        """
        Stop the background services
        """
        del self.session
        self.msl_server.server_close()
        self.msl_server.shutdown()
        self.msl_server = None
        self.msl_thread.join()
        self.msl_thread = None
        common.info('Stopped MSL Service')

    def run(self):
        """
        Main loop. Runs until xbmc.Monitor requests abort
        """
        self.start_services()
        player = xbmc.Player()

        while not self.controller.abortRequested():
            # pylint: disable=broad-except
            try:
                if player.isPlayingVideo():
                    self.controller.on_playback_tick()
                self.library_updater.on_tick()
            except Exception as exc:
                common.error(exc)

            if self.controller.waitForAbort(1):
                break

        self.shutdown()


if __name__ == '__main__':
    NetflixService().run()
