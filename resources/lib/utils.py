# -*- coding: utf-8 -*-
# Module: utils
# Created on: 13.01.2017

"""General utils"""

import time
import hashlib
import platform
from functools import wraps
from types import FunctionType
import xbmc


class LoggingComponent(object):
    """
    Prepends log statements with the calling class' name
    """
    # pylint: disable=too-few-public-methods
    def __init__(self, nx_common):
        self._log = nx_common.log

    def log(self, msg, level=xbmc.LOGDEBUG):
        """
        Log a message
        """
        self._log('{}: {}'.format(self.__class__.__name__, msg), level)


def noop(**kwargs):
    """Takes everything, does nothing, classic no operation function"""
    return kwargs


def log(func):
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
        arguments = ''
        for key, value in kwargs.iteritems():
            if key != 'account' and key != 'credentials':
                arguments += ":%s = %s:" % (key, value)
        if arguments != '':
            that.log('"' + class_name + '::' + name +
                     '" called with arguments ' + arguments)
        else:
            that.log('"' + class_name + '::' + name + '" called')
        result = func(*args, **kwargs)
        that.log('"' + class_name + '::' + name + '" returned: ' + str(result))
        return result

    wrapped.__doc__ = func.__doc__
    return wrapped


def get_user_agent():
    """
    Determines the user agent string for the current platform.
    Needed to retrieve a valid ESN (except for Android, where the ESN can
    be generated locally)

    :returns: str -- User agent string
    """
    chrome_version = 'Chrome/59.0.3071.115'
    base = 'Mozilla/5.0 '
    base += '%PL% '
    base += 'AppleWebKit/537.36 (KHTML, like Gecko) '
    base += '%CH_VER% Safari/537.36'.replace('%CH_VER%', chrome_version)
    system = platform.system()
    # Mac OSX
    if system == 'Darwin':
        return base.replace('%PL%', '(Macintosh; Intel Mac OS X 10_10_1)')
    # Windows
    if system == 'Windows':
        return base.replace('%PL%', '(Windows NT 6.1; WOW64)')
    # ARM based Linux
    if platform.machine().startswith('arm'):
        return base.replace('%PL%', '(X11; CrOS armv7l 7647.78.0)')
    # x86 Linux
    return base.replace('%PL%', '(X11; Linux x86_64)')


def uniq_id(delay=1):
    """
    Returns a unique id based on the devices MAC address

    :param delay: Retry delay in sec
    :type delay: int
    :returns:  string -- Unique secret
    """
    mac_addr = __get_mac_address(delay=delay)
    if ':' in mac_addr and delay == 2:
        return hashlib.sha256(str(mac_addr).encode()).digest()
    else:
        return hashlib.sha256('UnsafeStaticSecret'.encode()).digest()


def __get_mac_address(delay=1):
    """
    Returns the users mac address

    :param delay: retry delay in sec
    :type delay: int
    :returns:  string -- Devices MAC address
    """
    mac_addr = xbmc.getInfoLabel('Network.MacAddress')
    # hack response busy
    i = 0
    while ':' not in mac_addr and i < 3:
        i += 1
        time.sleep(delay)
        mac_addr = xbmc.getInfoLabel('Network.MacAddress')
    return mac_addr


def get_class_methods(class_item=None):
    """
    Returns the class methods of agiven class object

    :param class_item: Class item to introspect
    :type class_item: object
    :returns: list -- Class methods
    """
    _type = FunctionType
    return [x for x, y in class_item.__dict__.items() if isinstance(y, _type)]


def find_episode(episode_id, seasons):
    """
    Return metadata for a specific episode from within a nested
    metadata dict.
    Returns an empty dict if the episode could not be found.
    """
    for season in seasons:
        for episode in season['episodes']:
            if str(episode['id']) == episode_id:
                return episode
    return {}
