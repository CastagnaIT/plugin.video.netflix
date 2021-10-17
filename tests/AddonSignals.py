# -*- coding: utf-8 -*-
"""
    Copyright (C) 2019 Dag Wieers (@dagwieers) <dag@wieers.com>

    SPDX-License-Identifier: GPL-3.0-only
    See LICENSES/GPL-3.0-only.md for more information.
"""
import binascii
import json
import time

xbmc = __import__('xbmc')
xbmcaddon = __import__('xbmcaddon')

RECEIVER = None


class WaitTimeoutError(Exception):
    pass


def _getReceiver():
    global RECEIVER  # pylint: disable=global-statement
    if not RECEIVER:
        RECEIVER = SignalReceiver()
    return RECEIVER


def _decodeData(data):
    data = json.loads(data)
    if data:
        return json.loads(binascii.unhexlify(data[0]))
    return None


def _encodeData(data):
    return f'\\"[\\"{binascii.hexlify(json.dumps(data))}\\"]\\"'


class SignalReceiver(xbmc.Monitor):
    def __init__(self):  # pylint: disable=super-init-not-called
        self._slots = {}

    def registerSlot(self, signaler_id, signal, callback):
        if signaler_id not in self._slots:
            self._slots[signaler_id] = {}
        self._slots[signaler_id][signal] = callback

    def unRegisterSlot(self, signaler_id, signal):
        if signaler_id not in self._slots:
            return
        if signal not in self._slots[signaler_id]:
            return
        del self._slots[signaler_id][signal]

    def onNotification(self, sender, method, data):
        if not sender[-7:] == '.SIGNAL':
            return
        sender = sender[:-7]
        if sender not in self._slots:
            return
        signal = method.split('.', 1)[-1]
        if signal not in self._slots[sender]:
            return
        self._slots[sender][signal](_decodeData(data))


class CallHandler:
    def __init__(self, signal, data, source_id, timeout=1000, use_timeout_exception=False):
        self.signal = signal
        self.data = data
        self.timeout = timeout
        self.sourceID = source_id
        self._return = None
        self.is_callback_received = False
        self.use_timeout_exception = use_timeout_exception
        registerSlot(self.sourceID, f'_return.{self.signal}', self.callback)
        sendSignal(signal, data, self.sourceID)

    def callback(self, data):
        self._return = data
        self.is_callback_received = True

    def waitForReturn(self):
        monitor = xbmc.Monitor()
        end_time = time.perf_counter() + (self.timeout / 1000)
        while not self.is_callback_received:
            if time.perf_counter() > end_time:
                if self.use_timeout_exception:
                    unRegisterSlot(self.sourceID, self.signal)
                    raise WaitTimeoutError
                break
            if monitor.abortRequested():
                raise OSError
            xbmc.sleep(10)
        unRegisterSlot(self.sourceID, self.signal)
        return self._return


def registerSlot(signaler_id, signal, callback):
    receiver = _getReceiver()
    receiver.registerSlot(signaler_id, signal, callback)


def unRegisterSlot(signaler_id, signal):
    receiver = _getReceiver()
    receiver.unRegisterSlot(signaler_id, signal)


def sendSignal(signal, data=None, source_id=None, sourceID=None):
    if sourceID:
        xbmc.log('++++==== script.module.addon.signals: sourceID keyword is DEPRECATED - use source_id ====++++', xbmc.LOGNOTICE)
    source_id = source_id or sourceID or xbmcaddon.Addon().getAddonInfo('id')
    command = f'XBMC.NotifyAll({source_id}.SIGNAL,{signal},{_encodeData(data)})'
    xbmc.executebuiltin(command)


def registerCall(signaler_id, signal, callback):
    registerSlot(signaler_id, signal, callback)


def returnCall(signal, data=None, source_id=None):
    sendSignal(f'_return.{signal}', data, source_id)


def makeCall(signal, data=None, source_id=None, timeout_ms=1000, use_timeout_exception=False):
    return CallHandler(signal, data, source_id, timeout_ms, use_timeout_exception).waitForReturn()
