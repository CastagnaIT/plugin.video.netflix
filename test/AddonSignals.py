# -*- coding: utf-8 -*-
import xbmc
import xbmcaddon
import binascii
import json

RECEIVER = None


def _getReceiver():
    global RECEIVER
    if not RECEIVER:
        RECEIVER = SignalReceiver()
    return RECEIVER


def _decodeData(data):
    data = json.loads(data)
    if data:
        return json.loads(binascii.unhexlify(data[0]))


def _encodeData(data):
    return '\\"[\\"{0}\\"]\\"'.format(binascii.hexlify(json.dumps(data)))


class SignalReceiver(xbmc.Monitor):
    def __init__(self):
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
    def __init__(self, signal, data, source_id, timeout=1000):
        self.signal = signal
        self.data = data
        self.timeout = timeout
        self.sourceID = source_id
        self._return = None
        registerSlot(self.sourceID, '_return.{0}'.format(self.signal), self.callback)
        sendSignal(signal, data, self.sourceID)

    def callback(self, data):
        self._return = data

    def waitForReturn(self):
        waited = 0
        while waited < self.timeout:
            if self._return is not None:
                break
            xbmc.sleep(100)
            waited += 100

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
    command = 'XBMC.NotifyAll({0}.SIGNAL,{1},{2})'.format(source_id, signal,_encodeData(data))
    xbmc.executebuiltin(command)


def registerCall(signaler_id, signal, callback):
    registerSlot(signaler_id, signal, callback)


def returnCall(signal, data=None, source_id=None):
    sendSignal('_return.{0}'.format(signal), data, source_id)


def makeCall(signal, data=None, source_id=None, timeout_ms=1000):
    return CallHandler(signal, data, source_id, timeout_ms).waitForReturn()
