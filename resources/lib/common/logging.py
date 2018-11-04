# -*- coding: utf-8 -*-
"""Helper functions for logging"""
from __future__ import unicode_literals

from functools import wraps

import xbmc

from resources.lib.globals import g


def log(msg, exc=None, level=xbmc.LOGDEBUG):
    """Log a message to the Kodi logfile.
    If msg contains a format placeholder for exc and exc is not none,
    exc will be formatted into the message."""
    msg = msg.format(exc=exc) if exc is not None and '{exc}' in msg else msg
    if isinstance(msg, str):
        msg = msg.decode('utf-8')
    xbmc.log('[{identifier} ({handle})] {msg}'
             .format(identifier=g.ADDON_ID, handle=g.PLUGIN_HANDLE, msg=msg)
             .encode('utf-8'),
             level)


def debug(msg='{exc}', exc=None):
    """Log a debug message."""
    log(msg, exc, xbmc.LOGDEBUG)


def info(msg='{exc}', exc=None):
    """Log an info message."""
    log(msg, exc, xbmc.LOGINFO)


def warn(msg='{exc}', exc=None):
    """Log a warning message."""
    log(msg, exc, xbmc.LOGWARNING)


def error(msg='{exc}', exc=None):
    """Log an error message."""
    log(msg, exc, xbmc.LOGERROR)


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
        that = args[0]
        class_name = that.__class__.__name__
        arguments = [':{} = {}:'.format(key, value)
                     for key, value in kwargs.iteritems()
                     if key not in ['account', 'credentials']]
        if arguments:
            log('{cls}::{method} called with arguments {args}'
                .format(cls=class_name, method=name, args=''.join(arguments)))
        else:
            log('{cls}::{method} called'.format(cls=class_name, method=name))
        result = func(*args, **kwargs)
        log('{cls}::{method} return {result}'
            .format(cls=class_name, method=name, result=result))
        return result

    wrapped.__doc__ = func.__doc__
    return wrapped
