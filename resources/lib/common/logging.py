# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Helper functions for logging

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import time
from functools import wraps
from future.utils import iteritems

import xbmc

from resources.lib.globals import g

__LOG_LEVEL__ = None


def perf_clock():
    if hasattr(time, 'clock'):
        # time.clock() was deprecated in Python 3.3 and removed in Python 3.8
        return time.clock()  # pylint: disable=no-member
    if hasattr(time, 'perf_counter'):
        # * 1e-6 convert [us] to [s]
        return time.perf_counter() * 1e-6  # pylint: disable=no-member
    return time.time()


def get_log_level():
    """
    Lazily read the log level settings
    """
    # pylint: disable=global-statement
    global __LOG_LEVEL__
    if __LOG_LEVEL__ is None:
        try:
            __LOG_LEVEL__ = g.ADDON.getSettingString('debug_log_level')
            if __LOG_LEVEL__ != 'Disabled':
                _log('Debug logging level is {}'.format(__LOG_LEVEL__), xbmc.LOGINFO)
        except Exception:  # pylint: disable=broad-except
            # If settings.xml was not created yet, as at first service run
            # g.ADDON.getSettingString('debug_log_level') will thrown a TypeError
            # If any other error appears, we don't want the service to crash,
            # let's return 'Disabled' in all case
            __LOG_LEVEL__ = 'Disabled'
    return __LOG_LEVEL__


def is_debug_verbose():
    return get_log_level() == 'Verbose'


def reset_log_level_global_var():
    """Reset log level global var, in order to update the value from settings"""
    # pylint: disable=global-statement
    global __LOG_LEVEL__
    __LOG_LEVEL__ = None


def _log(msg, level, *args, **kwargs):
    """Log a message to the Kodi logfile."""
    if args or kwargs:
        msg = msg.format(*args, **kwargs)
    xbmc.log(g.py2_encode(
        '[{identifier} ({handle})] {msg}'.format(identifier=g.ADDON_ID,
                                                 handle=g.PLUGIN_HANDLE,
                                                 msg=msg)),
             level)


def debug(msg, *args, **kwargs):
    """Log a debug message."""
    if get_log_level() != 'Verbose':
        return
    _log(msg, xbmc.LOGDEBUG, *args, **kwargs)


def info(msg, *args, **kwargs):
    """Log an info message."""
    if get_log_level() == 'Disabled':
        return
    _log(msg, xbmc.LOGINFO, *args, **kwargs)


def warn(msg, *args, **kwargs):
    """Log a warning message."""
    if get_log_level() == 'Disabled':
        return
    _log(msg, xbmc.LOGWARNING, *args, **kwargs)


def error(msg, *args, **kwargs):
    """Log an error message."""
    _log(msg, xbmc.LOGERROR, *args, **kwargs)


def logdetails(func):
    """
    Log decarator that is used to annotate methods & output everything to the Kodi debug log

    :param delay: retry delay in sec
    :type delay: int
    :returns:  string -- Devices MAC address
    """
    name = func.func_name

    @wraps(func)
    def wrapped(*args, **kwargs):
        """Wrapper function to maintain correct stack traces"""
        that = args[0]
        class_name = that.__class__.__name__
        arguments = [':{} = {}:'.format(key, value)
                     for key, value in iteritems(kwargs)
                     if key not in ['account', 'credentials']]
        if arguments:
            _log('{cls}::{method} called with arguments {args}'
                 .format(cls=class_name, method=name, args=''.join(arguments)),
                 xbmc.LOGDEBUG)
        else:
            _log('{cls}::{method} called'.format(cls=class_name, method=name),
                 xbmc.LOGDEBUG)
        result = func(*args, **kwargs)
        _log('{cls}::{method} return {result}'
             .format(cls=class_name, method=name, result=result),
             xbmc.LOGDEBUG)
        return result

    wrapped.__doc__ = func.__doc__
    return wrapped


def time_execution(immediate):
    """A decorator that wraps a function call and times its execution"""
    # pylint: disable=missing-docstring
    def time_execution_decorator(func):
        @wraps(func)
        def timing_wrapper(*args, **kwargs):
            if not g.TIME_TRACE_ENABLED and not is_debug_verbose():
                return func(*args, **kwargs)

            g.add_time_trace_level()
            start = perf_clock()
            try:
                return func(*args, **kwargs)
            finally:
                execution_time = int((perf_clock() - start) * 1000)
                if immediate:
                    debug('Call to {} took {}ms'
                          .format(func.__name__, execution_time))
                else:
                    g.TIME_TRACE.append([func.__name__, execution_time,
                                         g.time_trace_level])
                g.remove_time_trace_level()
        return timing_wrapper
    return time_execution_decorator


def log_time_trace():
    """Write the time tracing info to the debug log"""
    if not is_debug_verbose() and not g.TIME_TRACE_ENABLED:
        return

    time_trace = ['Execution time info for this run:\n']
    g.TIME_TRACE.reverse()
    for trace in g.TIME_TRACE:
        time_trace.append(' ' * trace[2])
        time_trace.append(format(trace[0], '<30'))
        time_trace.append('{:>5} ms\n'.format(trace[1]))
    debug(''.join(time_trace))
    g.reset_time_trace()
