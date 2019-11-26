# -*- coding: utf-8 -*-
"""Helper functions for logging"""
from __future__ import absolute_import, division, unicode_literals
from functools import wraps

from resources.lib.globals import g

__LOG_LEVEL__ = None


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
                from xbmc import LOGINFO
                _log('Debug logging level is {}'.format(__LOG_LEVEL__), LOGINFO)
        except Exception:  # pylint: disable=broad-except
            # If settings.xml was not created yet, as at first service run
            # g.ADDON.getSettingString('debug_log_level') will thrown a TypeError
            # If any other error appears, we don't want the service to crash,
            # let's return 'Disabled' in all case
            __LOG_LEVEL__ = 'Disabled'
    return __LOG_LEVEL__


def reset_log_level_global_var():
    """Reset log level global var, in order to update the value from settings"""
    # pylint: disable=global-statement
    global __LOG_LEVEL__
    __LOG_LEVEL__ = None


def _log(msg, level, *args, **kwargs):
    """Log a message to the Kodi logfile."""
    from xbmc import log
    if args or kwargs:
        msg = msg.format(*args, **kwargs)
    log(g.py2_encode(
        '[{identifier} ({handle})] {msg}'.format(identifier=g.ADDON_ID,
                                                 handle=g.PLUGIN_HANDLE,
                                                 msg=msg)),
        level)


def debug(msg, *args, **kwargs):
    """Log a debug message."""
    if get_log_level() != 'Verbose':
        return
    from xbmc import LOGDEBUG
    _log(msg, LOGDEBUG, *args, **kwargs)


def info(msg, *args, **kwargs):
    """Log an info message."""
    if get_log_level() == 'Disabled':
        return
    from xbmc import LOGINFO
    _log(msg, LOGINFO, *args, **kwargs)


def warn(msg, *args, **kwargs):
    """Log a warning message."""
    if get_log_level() == 'Disabled':
        return
    from xbmc import LOGWARNING
    _log(msg, LOGWARNING, *args, **kwargs)


def error(msg, *args, **kwargs):
    """Log an error message."""
    from xbmc import LOGERROR
    _log(msg, LOGERROR, *args, **kwargs)


def logdetails(func):
    """
    Log decarator that is used to annotate methods & output everything to
    the Kodi debug log

    :param delay: retry delay in sec
    :type delay: int
    :returns:  string -- Devices MAC address
    """
    name = func.func_name

    @wraps(func)
    def wrapped(*args, **kwargs):
        """Wrapper function to maintain correct stack traces"""
        from xbmc import LOGDEBUG
        from future.utils import iteritems
        that = args[0]
        class_name = that.__class__.__name__
        arguments = [':{} = {}:'.format(key, value)
                     for key, value in iteritems(kwargs)
                     if key not in ['account', 'credentials']]
        if arguments:
            _log('{cls}::{method} called with arguments {args}'.format(cls=class_name, method=name, args=''.join(arguments)), LOGDEBUG)
        else:
            _log('{cls}::{method} called'.format(cls=class_name, method=name), LOGDEBUG)
        result = func(*args, **kwargs)
        _log('{cls}::{method} return {result}'.format(cls=class_name, method=name, result=result), LOGDEBUG)
        return result

    wrapped.__doc__ = func.__doc__
    return wrapped
