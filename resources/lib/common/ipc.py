# -*- coding: utf-8 -*-
"""Helper functions for inter-process communication via AddonSignals"""
from __future__ import unicode_literals

import traceback
from functools import wraps

import AddonSignals

from resources.lib.globals import g
import resources.lib.api.exceptions as apierrors

from .logging import debug, error
from .misc_utils import time_execution


class BackendNotReady(Exception):
    """The background services are not started yet"""
    pass


class Signals(object):
    """Signal names for use with AddonSignals"""
    # pylint: disable=too-few-public-methods
    PLAYBACK_INITIATED = 'playback_initiated'
    ESN_CHANGED = 'esn_changed'
    LIBRARY_UPDATE_REQUESTED = 'library_update_requested'


def register_slot(callback, signal=None, source_id=None):
    """Register a callback with AddonSignals for return calls"""
    name = signal if signal else _signal_name(callback)
    AddonSignals.registerSlot(
        signaler_id=source_id or g.ADDON_ID,
        signal=name,
        callback=callback)
    debug('Registered AddonSignals slot {} to {}'.format(name, callback))


def unregister_slot(callback, signal=None):
    """Remove a registered callback from AddonSignals"""
    name = signal if signal else _signal_name(callback)
    AddonSignals.unRegisterSlot(
        signaler_id=g.ADDON_ID,
        signal=name)
    debug('Unregistered AddonSignals slot {}'.format(name))


def send_signal(signal, data=None):
    """Send a signal via AddonSignals"""
    AddonSignals.sendSignal(
        source_id=g.ADDON_ID,
        signal=signal,
        data=data)


@time_execution(immediate=False)
def make_call(callname, data=None):
    if g.IPC_OVER_HTTP:
        return make_http_call(callname, data)
    return make_addonsignals_call(callname, data)


def make_http_call(callname, data):
    """Make an IPC call via HTTP and wait for it to return.
    The contents of data will be expanded to kwargs and passed into the target
    function."""
    from collections import OrderedDict
    import urllib2
    import json
    debug('Handling HTTP IPC call to {}'.format(callname))
    # don't use proxy for localhost
    url = 'http://127.0.0.1:{}/{}'.format(
        g.LOCAL_DB.get_value('ns_service_port', 8001), callname)
    urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler({})))
    try:
        result = json.loads(
            urllib2.urlopen(url=url, data=json.dumps(data)).read(),
            object_pairs_hook=OrderedDict)
    except urllib2.URLError:
        raise BackendNotReady
    _raise_for_error(callname, result)
    return result


def make_addonsignals_call(callname, data):
    """Make an IPC call via AddonSignals and wait for it to return.
    The contents of data will be expanded to kwargs and passed into the target
    function."""
    debug('Handling AddonSignals IPC call to {}'.format(callname))
    result = AddonSignals.makeCall(
        source_id=g.ADDON_ID,
        signal=callname,
        data=data,
        timeout_ms=16000)
    _raise_for_error(callname, result)
    if result is None:
        raise Exception('AddonSignals call timed out')
    return result


def _raise_for_error(callname, result):
    if isinstance(result, dict) and 'error' in result:
        error('IPC call {callname} returned {error}: {message}'
              .format(callname=callname, **result))
        try:
            raise apierrors.__dict__[result['error']](result['message'])
        except KeyError:
            raise Exception(result['error'])


def addonsignals_return_call(func):
    """Makes func return callable through AddonSignals and
    handles catching, conversion and forwarding of exceptions"""
    @wraps(func)
    def make_return_call(instance, data):
        """Makes func return callable through AddonSignals and
        handles catching, conversion and forwarding of exceptions"""
        # pylint: disable=broad-except
        try:
            result = call(instance, func, data)
        except Exception as exc:
            error('IPC callback raised exception: {exc}', exc)
            error(traceback.format_exc())
            result = {
                'error': exc.__class__.__name__,
                'message': exc.__unicode__()
            }
        if g.IPC_OVER_HTTP:
            return result
        # Do not return None or AddonSignals will keep waiting till timeout
        if result is None:
            result = False
        AddonSignals.returnCall(
            signal=_signal_name(func), source_id=g.ADDON_ID, data=result)
    return make_return_call


def call(instance, func, data):
    if isinstance(data, dict):
        return func(instance, **data)
    elif data is not None:
        return func(instance, data)
    return func(instance)


def _signal_name(func):
    return func.__name__
