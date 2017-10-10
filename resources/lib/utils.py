#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: utils
# Created on: 13.01.2017

import time
import hashlib
import platform
import xbmc


# Takes everything, does nothing, classic no operation function
def noop (**kwargs):
    return True

# log decorator
def log(f, name=None):
    if name is None:
        name = f.func_name
    def wrapped(*args, **kwargs):
        that = args[0]
        class_name = that.__class__.__name__
        arguments = ''
        for key, value in kwargs.iteritems():
            if key != 'account' and key != 'credentials':
                arguments += ":%s = %s:" % (key, value)
        if arguments != '':
            that.log('"' + class_name + '::' + name + '" called with arguments ' + arguments)
        else:
            that.log('"' + class_name + '::' + name + '" called')
        result = f(*args, **kwargs)
        that.log('"' + class_name + '::' + name + '" returned: ' + str(result))
        return result
    wrapped.__doc__ = f.__doc__
    return wrapped

def get_user_agent_for_current_platform():
    """Determines the user agent string for the current platform (to retrieve a valid ESN)

    Returns
    -------
    :obj:`str`
        User Agent for platform
    """
    system = platform.system()
    if system == 'Darwin':
        return 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'
    if system == 'Windows':
        return 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'
    if platform.machine().startswith('arm'):
        return 'Mozilla/5.0 (X11; CrOS armv7l 7647.78.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'
    return 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'

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
