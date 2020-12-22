# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for inter-process communication via AddonSignals

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json
from functools import wraps

import AddonSignals

from resources.lib.common import exceptions
from resources.lib.globals import G
from resources.lib.utils.logging import LOG, measure_exec_time_decorator
from .misc_utils import run_threaded

IPC_TIMEOUT_SECS = 20
IPC_EXCEPTION_PLACEHOLDER = 'IPC_EXCEPTION_PLACEHOLDER'


class Signals:  # pylint: disable=no-init
    """Signal names for use with AddonSignals"""
    # pylint: disable=too-few-public-methods
    PLAYBACK_INITIATED = 'playback_initiated'
    RELEASE_LICENSE = 'release_license'
    REQUEST_KODI_LIBRARY_UPDATE = 'request_kodi_library_update'
    UPNEXT_ADDON_INIT = 'upnext_data'
    QUEUE_VIDEO_EVENT = 'queue_video_event'
    CLEAR_USER_ID_TOKENS = 'clean_user_id_tokens'
    REINITIALIZE_MSL_HANDLER = 'reinitialize_msl_handler'
    SWITCH_EVENTS_HANDLER = 'switch_events_handler'


def register_slot(callback, signal=None, source_id=None):
    """Register a callback with AddonSignals for return calls"""
    name = signal if signal else callback.__name__
    AddonSignals.registerSlot(
        signaler_id=source_id or G.ADDON_ID,
        signal=name,
        callback=callback)
    LOG.debug('Registered AddonSignals slot {} to {}'.format(name, callback))


def unregister_slot(callback, signal=None):
    """Remove a registered callback from AddonSignals"""
    name = signal if signal else callback.__name__
    AddonSignals.unRegisterSlot(
        signaler_id=G.ADDON_ID,
        signal=name)
    LOG.debug('Unregistered AddonSignals slot {}'.format(name))


def send_signal(signal, data=None, non_blocking=False):
    """Send a signal via AddonSignals"""
    # Using sendSignal of AddonSignals you might think that it is not a blocking call instead is blocking because it
    # uses executeJSONRPC that is a blocking call, so the invoker will remain blocked until the function called by
    # executeJSONRPC has completed his operations, even if it does not return any data.
    # This workaround call sendSignal in a separate thread so immediately releases the invoker.
    # This is to be considered according to the functions to be called,
    # because it could keep the caller blocked for a certain amount of time unnecessarily.
    # To note that several consecutive calls, are made in sequence not at the same time.
    run_threaded(non_blocking, _send_signal, signal, data)


def _send_signal(signal, data):
    AddonSignals.sendSignal(
        source_id=G.ADDON_ID,
        signal=signal,
        data=data)


@measure_exec_time_decorator()
def make_call(callname, data=None, port_setting_name='ns_service_port'):
    # Note: IPC over HTTP handle FULL objects serialization, AddonSignals NOT HANDLE the serialization of objects
    if G.IPC_OVER_HTTP:
        return make_http_call(callname, data, port_setting_name)
    return make_addonsignals_call(callname, data)


def make_http_call(callname, data, port_setting_name='ns_service_port'):
    """Make an IPC call via HTTP and wait for it to return.
    The contents of data will be expanded to kwargs and passed into the target function."""
    from collections import OrderedDict
    from urllib.request import build_opener, install_opener, ProxyHandler, HTTPError, URLError, urlopen
    LOG.debug('Handling HTTP IPC call to {}'.format(callname))
    # Note: On python 3, using 'localhost' slowdown the call (Windows OS is affected) not sure if it is an urllib issue
    url = 'http://127.0.0.1:{}/{}'.format(G.LOCAL_DB.get_value(port_setting_name), callname)
    install_opener(build_opener(ProxyHandler({})))  # don't use proxy for localhost
    try:
        result = json.loads(
            urlopen(url=url, data=json.dumps(data).encode('utf-8'), timeout=IPC_TIMEOUT_SECS).read(),
            object_pairs_hook=OrderedDict)
    except HTTPError as exc:
        result = json.loads(exc.reason)
    except URLError as exc:
        err_msg = str(exc)
        if '10049' in err_msg:
            err_msg += '\r\nPossible cause is wrong localhost settings in your operative system.'
        LOG.error(err_msg)
        raise exceptions.BackendNotReady(err_msg) from exc
    _raise_for_error(result)
    return result


def make_http_call_cache(callname, params, data):
    """Make an IPC call via HTTP and wait for it to return.
    The contents of data will be expanded to kwargs and passed into the target function."""
    from urllib.request import build_opener, install_opener, ProxyHandler, HTTPError, URLError, Request, urlopen
    # debug('Handling HTTP IPC call to {}'.format(callname))
    # Note: On python 3, using 'localhost' slowdown the call (Windows OS is affected) not sure if it is an urllib issue
    url = 'http://127.0.0.1:{}/{}'.format(G.LOCAL_DB.get_value('cache_service_port', 8002), callname)
    install_opener(build_opener(ProxyHandler({})))  # don't use proxy for localhost
    r = Request(url=url, data=data, headers={'Params': json.dumps(params)})
    try:
        result = urlopen(r, timeout=IPC_TIMEOUT_SECS).read()
    except HTTPError as exc:
        if exc.reason in exceptions.__dict__:
            raise exceptions.__dict__[exc.reason] from exc
        raise Exception('The service has returned: {}'.format(exc.reason)) from exc
    except URLError as exc:
        err_msg = str(exc)
        if '10049' in err_msg:
            err_msg += '\r\nPossible cause is wrong localhost settings in your operative system.'
        LOG.error(err_msg)
        raise exceptions.BackendNotReady(err_msg) from exc
    return result


def make_addonsignals_call(callname, data):
    """Make an IPC call via AddonSignals and wait for it to return.
    The contents of data will be expanded to kwargs and passed into the target
    function."""
    LOG.debug('Handling AddonSignals IPC call to {}'.format(callname))
    result = AddonSignals.makeCall(
        source_id=G.ADDON_ID,
        signal=callname,
        data=data,
        timeout_ms=IPC_TIMEOUT_SECS * 1000)
    _raise_for_error(result)
    if result is None:
        raise Exception('Addon Signals call timeout')
    return result


def _raise_for_error(result):
    # The json exception data format is set by ipc_convert_exc_to_json function
    if isinstance(result, dict) and IPC_EXCEPTION_PLACEHOLDER in result:
        result = result[IPC_EXCEPTION_PLACEHOLDER]
        if result['class'] in exceptions.__dict__:
            raise exceptions.__dict__[result['class']](result['message'])
        raise Exception(result['class'] + '\r\nError details:\r\n' + result.get('message', '--'))


def ipc_return_call(func):
    """
    Decorator to make a func return callable through IPC
    and handles catching, conversion and forwarding of exceptions
    """
    @wraps(func)
    def make_return_call(instance, data):
        _perform_ipc_return_call_instance(instance, func, data)
    return make_return_call


class EnvelopeIPCReturnCall:
    """Makes a function callable through IPC and handles catching, conversion and forwarding of exceptions"""
    # Defines a type of in-memory reference to avoids define functions in the source code just to handle IPC return call
    def __init__(self, func):
        self._func = func

    def call(self, data):
        """Routes the call to the function associated to the class"""
        return _perform_ipc_return_call(self._func, data, self._func.__name__)


def _perform_ipc_return_call_instance(instance, func, data):
    try:
        result = _call_with_instance(instance, func, data)
    except Exception as exc:  # pylint: disable=broad-except
        if exc.__class__.__name__ not in ['CacheMiss', 'MetadataNotAvailable']:
            LOG.error('IPC callback raised exception: {exc}', exc=exc)
            import traceback
            LOG.error(traceback.format_exc())
        result = ipc_convert_exc_to_json(exc)
    return _execute_addonsignals_return_call(result, func.__name__)


def _perform_ipc_return_call(func, data, func_name=None):
    try:
        result = _call(func, data)
    except Exception as exc:  # pylint: disable=broad-except
        if exc.__class__.__name__ not in ['CacheMiss', 'MetadataNotAvailable']:
            LOG.error('IPC callback raised exception: {exc}', exc=exc)
            import traceback
            LOG.error(traceback.format_exc())
        result = ipc_convert_exc_to_json(exc)
    return _execute_addonsignals_return_call(result, func_name)


def ipc_convert_exc_to_json(exc=None, class_name=None, message=None):
    """
    Convert an exception to a json data exception
    :param exc: exception class

    or else, build a json data exception
    :param class_name: custom class name
    :param message: custom message
    """
    return {IPC_EXCEPTION_PLACEHOLDER: {
        'class': class_name or exc.__class__.__name__,
        'message': message or str(exc),
    }}


def _execute_addonsignals_return_call(result, func_name):
    """If enabled execute AddonSignals return callback"""
    if G.IPC_OVER_HTTP:
        return result
    # Do not return None or AddonSignals will keep waiting till timeout
    if result is None:
        result = {}
    AddonSignals.returnCall(signal=func_name, source_id=G.ADDON_ID, data=result)
    return result


def _call(func, data):
    if isinstance(data, dict):
        return func(**data)
    if data is not None:
        return func(data)
    return func()


def _call_with_instance(instance, func, data):
    if isinstance(data, dict):
        return func(instance, **data)
    if data is not None:
        return func(instance, data)
    return func(instance)
