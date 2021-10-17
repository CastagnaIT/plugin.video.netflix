# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2020 Stefano Gottardo
    Logging and measuring execution times

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import time
from functools import wraps

import xbmc


class Logging:
    """A helper class for logging"""

    def __init__(self):
        self.__addon_id = None
        self.__plugin_handle = None
        self.is_enabled = None
        self.is_time_trace_enabled = False
        self.time_trace_level = -2
        self.__time_trace_data = []
        self.debug = self._debug
        self.info = self._info
        self.warn = self._warn

    def initialize(self, addon_id, plugin_handle, is_enabled, is_time_trace_enabled):
        if is_enabled == self.is_enabled and is_time_trace_enabled == self.is_time_trace_enabled:
            return
        self.__addon_id = addon_id
        self.__plugin_handle = plugin_handle
        self.__log(f'The debug logging is set as {"ENABLED" if is_enabled else "DISABLED"}', xbmc.LOGINFO)
        self.is_enabled = is_enabled
        self.is_time_trace_enabled = is_enabled and is_time_trace_enabled
        if is_enabled:
            self.info = self._info
            self.warn = self._warn
            self.debug = self._debug
        else:
            # To avoid adding extra workload to the cpu when logging is not required,
            # we replace the log methods with a empty method
            self.info = self.__not_to_process
            self.warn = self.__not_to_process
            self.debug = self.__not_to_process

    def __log(self, msg, log_level, *args, **kwargs):
        """Log a message to the Kodi logfile."""
        if args or kwargs:
            msg = msg.format(*args, **kwargs)
        message = f'[{self.__addon_id} ({self.__plugin_handle})] {msg}'
        xbmc.log(message, log_level)

    def _debug(self, msg, *args, **kwargs):
        """Log a debug message."""
        self.__log(msg, xbmc.LOGDEBUG, *args, **kwargs)

    def _info(self, msg, *args, **kwargs):
        """Log an info message."""
        self.__log(msg, xbmc.LOGINFO, *args, **kwargs)

    def _warn(self, msg, *args, **kwargs):
        """Log a warning message."""
        self.__log(msg, xbmc.LOGWARNING, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        """Log an error message."""
        self.__log(msg, xbmc.LOGERROR, *args, **kwargs)

    def __not_to_process(self, msg, *args, **kwargs):
        pass

    def add_time_trace_level(self):
        """Add a level to the time trace"""
        self.time_trace_level += 2

    def remove_time_trace_level(self):
        """Remove a level from the time trace"""
        self.time_trace_level -= 2

    def add_time_trace(self, func_name, execution_time):
        self.__time_trace_data.append([func_name, execution_time, self.time_trace_level])

    def reset_time_trace(self):
        """Reset current time trace info"""
        self.__time_trace_data = []
        self.time_trace_level = -2

    def log_time_trace(self):
        """Write the time tracing info to the debug log"""
        if not self.is_time_trace_enabled:
            return
        time_trace = ['Execution time measured for this run:\n']
        self.__time_trace_data.reverse()
        for trace in self.__time_trace_data:
            time_trace.append(' ' * trace[2])
            time_trace.append(format(trace[0], '<30'))
            time_trace.append(f'{trace[1]:>5} ms\n')
        self.debug(''.join(time_trace))
        self.reset_time_trace()


def logdetails_decorator(func):
    """Log decorator that is used to annotate methods & output everything to the Kodi debug log"""
    name = func.__name__

    @wraps(func)
    def wrapped(*args, **kwargs):
        """Wrapper function to maintain correct stack traces"""
        that = args[0]
        class_name = that.__class__.__name__
        arguments = [f':{key} = {value}:'
                     for key, value in kwargs.items()
                     if key not in ['account', 'credentials']]
        if arguments:
            LOG.debug('{cls}::{method} called with arguments {args}',
                      cls=class_name, method=name, args=''.join(arguments))
        else:
            LOG.debug('{cls}::{method} called',
                      cls=class_name, method=name)
        result = func(*args, **kwargs)
        LOG.debug('{cls}::{method} return {result}',
                  cls=class_name, method=name, result=result)
        return result
    wrapped.__doc__ = func.__doc__
    return wrapped


def measure_exec_time_decorator(is_immediate=False):
    """A decorator that wraps a function call and times its execution"""
    # pylint: disable=missing-docstring
    def exec_time_decorator(func):
        @wraps(func)
        def timing_wrapper(*args, **kwargs):
            if not LOG.is_time_trace_enabled:
                return func(*args, **kwargs)
            LOG.add_time_trace_level()
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                execution_time = int((time.perf_counter() - start) * 1000)
                if is_immediate:
                    LOG.debug('Call to {} took {}ms', func.__name__, execution_time)
                else:
                    LOG.add_time_trace(func.__name__, execution_time)
                LOG.remove_time_trace_level()
        return timing_wrapper
    return exec_time_decorator


LOG = Logging()
