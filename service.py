# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: service
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""
from __future__ import unicode_literals

import threading

import xbmc

import resources.lib.common as common
import resources.lib.services as services
from resources.lib.services.nfsession import NetflixSession

SERVERS = {
    'msl': services.MSLTCPServer,
    #'ns': services.NetflixTCPServer
}

class NetflixService(object):
    """
    Netflix addon service
    """
    def __init__(self):
        self.servers = {}
        self.session = None
        for name, server_class in SERVERS.items():
            server_class.allow_reuse_address = True
            instance = server_class(('127.0.0.1', common.select_port(name)))
            thread = threading.Thread(target=instance.serve_forever)
            self.servers[name] = {'instance': instance, 'thread': thread}

    def start_servers(self):
        """
        Start the background services
        """
        self.session = NetflixSession()
        for name, components in self.servers.items():
            components['instance'].server_activate()
            components['instance'].timeout = 1
            components['thread'].start()
            common.info('[{}] Thread started'.format(name))

    def shutdown(self):
        """
        Stop the background services
        """
        del self.session
        for name, components in self.servers:
            components['instance'].server_close()
            components['instance'].shutdown()
            components['thread'].join()
            del self.servers['name']
            common.info('Stopped {} Service'.format(name.upper()))

    def run(self):
        """
        Main loop. Runs until xbmc.Monitor requests abort
        """
        self.start_servers()
        controller = services.PlaybackController()
        library_updater = services.LibraryUpdateService()
        player = xbmc.Player()

        while not controller.abortRequested():
            # pylint: disable=broad-except
            try:
                # if self.servers['ns']['instance'].esn_changed():
                #     self.servers['msl']['instance'].reset_msl_data()
                if player.isPlayingVideo():
                    controller.on_playback_tick()
                library_updater.on_tick()
            except Exception as exc:
                common.log(exc)

            if controller.waitForAbort(1):
                break

        self.shutdown()


if __name__ == '__main__':
    NetflixService().run()
