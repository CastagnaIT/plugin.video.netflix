# -*- coding: utf-8 -*-
"""Helper functions for inter-process communication via AddonSignals"""
from __future__ import unicode_literals

import traceback
from functools import wraps
from time import time

import AddonSignals

from resources.lib.globals import g
import resources.lib.api.exceptions as apierrors

from .logging import debug, error


class Signals(object):
    """Signal names for use with AddonSignals"""
    # pylint: disable=too-few-public-methods
    PLAYBACK_INITIATED = 'playback_initiated'
    ESN_CHANGED = 'esn_changed'


def register_slot(callback, signal=None):
    """Register a callback with AddonSignals for return calls"""
    name = signal if signal else _signal_name(callback)
    AddonSignals.registerSlot(
        signaler_id=g.ADDON_ID,
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


def make_call(callname, data=None):
    """Make a call via AddonSignals and wait for it to return.
    The contents of data will be expanded to kwargs and passed into the target
    function."""
    start = time()
    result = AddonSignals.makeCall(
        source_id=g.ADDON_ID,
        signal=callname,
        data=data,
        timeout_ms=10000)
    debug('AddonSignals call took {}s'.format(time() - start))
    if isinstance(result, dict) and 'error' in result:
        msg = ('AddonSignals call {callname} returned {error}: {message}'
               .format(callname=callname, **result))
        error(msg)
        try:
            raise apierrors.__dict__[result['error']](result['message'])
        except KeyError:
            raise Exception(result['error'])
    elif result is None:
        raise Exception('AddonSignals call timed out')
    return result


def addonsignals_return_call(func):
    """Makes func return callable through AddonSignals and
    handles catching, conversion and forwarding of exceptions"""
    @wraps(func)
    def make_return_call(instance, data):
        """Makes func return callable through AddonSignals and
        handles catching, conversion and forwarding of exceptions"""
        # pylint: disable=broad-except
        try:
            result = _call(instance, func, data)
        except Exception as exc:
            error('AddonSignals callback raised exception: {exc}', exc)
            error(traceback.format_exc())
            result = {
                'error': exc.__class__.__name__,
                'message': exc.__unicode__()
            }
        # Do not return None or AddonSignals will keep waiting till timeout
        if result is None:
            result = False
        AddonSignals.returnCall(
            signal=_signal_name(func), source_id=g.ADDON_ID, data=result)
    return make_return_call


def _call(instance, func, data):
    if isinstance(data, dict):
        return func(instance, **data)
    elif data is not None:
        return func(instance, data)
    return func(instance)


def _signal_name(func):
    return func.__name__
