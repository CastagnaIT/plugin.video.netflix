# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: service
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Kodi plugin for Netflix (https://netflix.com)"""


import threading
import socket
from SocketServer import TCPServer
from datetime import datetime, timedelta
import xbmc
from resources.lib.KodiHelper import KodiHelper
from resources.lib.KodiMonitor import KodiMonitor
from resources.lib.MSLHttpRequestHandler import MSLHttpRequestHandler
from resources.lib.NetflixHttpRequestHandler import NetflixHttpRequestHandler


def select_unused_port():
    """
    Helper function to select an unused port on the host machine

    :return: int - Free port
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    _, port = sock.getsockname()
    sock.close()
    return port


def strp(value, form):
    """
    Helper function to safely create datetime objects from strings

    :return: datetime - parsed datetime object
    """
    # pylint: disable=broad-except
    from time import strptime
    def_value = datetime.utcfromtimestamp(0)
    try:
        return datetime.strptime(value, form)
    except TypeError:
        try:
            return datetime(*(strptime(value, form)[0:6]))
        except ValueError:
            return def_value
    except Exception:
        return def_value


class NetflixService(object):
    """
    Netflix addon service
    """
    def __init__(self):
        # init kodi helper (for logging)
        self.kodi_helper = KodiHelper()

        self.last_schedule_check = datetime.now()
        self.schedule_check_interval = int(self.kodi_helper.get_setting(
            'schedule_check_interval'))
        self.startidle = 0
        self.freq = int('0' + self.kodi_helper.get_setting('auto_update'))

        # pick & store a port for the MSL service
        msl_port = select_unused_port()
        self.kodi_helper.set_setting('msl_service_port', str(msl_port))
        self.kodi_helper.log(msg='[MSL] Picked Port: ' + str(msl_port))

        # pick & store a port for the internal Netflix HTTP proxy service
        ns_port = select_unused_port()
        self.kodi_helper.set_setting('netflix_service_port', str(ns_port))
        self.kodi_helper.log(msg='[NS] Picked Port: ' + str(ns_port))

        # server defaults
        TCPServer.allow_reuse_address = True

        # configure the MSL Server
        self.msl_server = TCPServer(('127.0.0.1', msl_port),
                                    MSLHttpRequestHandler)
        self.msl_server.server_activate()
        self.msl_server.timeout = 1

        # configure the Netflix Data Server
        self.ns_server = TCPServer(('127.0.0.1', ns_port),
                                   NetflixHttpRequestHandler)
        self.ns_server.server_activate()
        self.ns_server.timeout = 1

    def _start_servers(self):
        # start thread for MLS servie
        msl_thread = threading.Thread(target=self.msl_server.serve_forever)
        msl_thread.daemon = True
        msl_thread.start()

        # start thread for Netflix HTTP service
        ns_thread = threading.Thread(target=self.ns_server.serve_forever)
        ns_thread.daemon = True
        ns_thread.start()

    def _shutdown(self):
        # MSL service shutdown sequence
        self.msl_server.server_close()
        self.msl_server.socket.close()
        self.msl_server.shutdown()
        self.kodi_helper.log(msg='Stopped MSL Service')

        # Netflix service shutdown sequence
        self.ns_server.server_close()
        self.ns_server.socket.close()
        self.ns_server.shutdown()
        self.kodi_helper.log(msg='Stopped HTTP Service')

    def _is_idle(self):
        if self.kodi_helper.get_setting('wait_idle') != 'true':
            return True

        lastidle = xbmc.getGlobalIdleTime()
        if xbmc.Player().isPlaying():
            self.startidle = lastidle
        if lastidle < self.startidle:
            self.startidle = 0
        idletime = lastidle - self.startidle
        return idletime >= 300

    def _update_running(self):
        update = self.kodi_helper.get_setting('update_running') or 'false'
        if update != 'false':
            starttime = strp(update, '%Y-%m-%d %H:%M')
            if (starttime + timedelta(hours=6)) <= datetime.now():
                self.kodi_helper.set_setting('update_running', 'false')
                self.kodi_helper.log(
                    'Canceling previous library update - duration > 6 hours',
                    xbmc.LOGWARNING)
            else:
                self.kodi_helper.log('DB Update already running')
                return True
        return False

    def run(self):
        """
        Main loop. Runs until xbmc.Monitor requests abort
        """
        self._start_servers()
        monitor = KodiMonitor(self.kodi_helper, self.kodi_helper.log)
        while not monitor.abortRequested():
            monitor.update_playback_progress()
            try:
                if self.library_update_scheduled() and self._is_idle():
                    self.update_library()
            except RuntimeError as exc:
                self.kodi_helper.log(
                    'RuntimeError: {}'.format(exc), xbmc.LOGERROR)
            if monitor.waitForAbort(5):
                break
        self._shutdown()

    def library_update_scheduled(self):
        """
        Checks if the scheduled time for a library update has been reached
        """
        now = datetime.now()
        next_schedule_check = (self.last_schedule_check +
                               timedelta(
                                   minutes=self.schedule_check_interval))

        if not self.freq or now <= next_schedule_check:
            self.kodi_helper.log('Auto-update disabled or schedule check '
                                 'interval not complete yet ({} / {}).'
                                 .format(now, next_schedule_check))
            return False

        self.last_schedule_check = now
        time = self.kodi_helper.get_setting('update_time') or '00:00'
        lastrun_date = (self.kodi_helper.get_setting('last_update') or
                        '1970-01-01')

        lastrun_full = lastrun_date + ' ' + time[0:5]
        lastrun = strp(lastrun_full, '%Y-%m-%d %H:%M')
        freqdays = [0, 1, 2, 5, 7][self.freq]
        nextrun = lastrun + timedelta(days=freqdays)

        self.kodi_helper.log(
            'It\'s currently {}, next run is scheduled for {}'
            .format(now, nextrun))

        return now >= nextrun

    def update_library(self):
        """
        Triggers an update of the local Kodi library
        """
        if not self._update_running():
            self.kodi_helper.log('Triggering library update', xbmc.LOGNOTICE)
            xbmc.executebuiltin(
                ('XBMC.RunPlugin(plugin://{}/?action=export-new-episodes'
                 '&inbackground=True)')
                .format(self.kodi_helper.get_addon().getAddonInfo('id')))


if __name__ == '__main__':
    NetflixService().run()
