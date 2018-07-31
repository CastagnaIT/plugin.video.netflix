# -*- coding: utf-8 -*-
# Module: utils
# Created on: 13.01.2017

"""General utils"""

import time
import hashlib
import platform
import json
from functools import wraps
from types import FunctionType
import xbmc


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


def json_rpc(method, params=None):
    """
    Executes a JSON-RPC in Kodi

    :param method: The JSON-RPC method to call
    :type method: string
    :param params: The parameters of the method call (optional)
    :type params: dict
    :returns: dict -- Method call result
    """
    request_data = {'jsonrpc': '2.0', 'method': method, 'id': 1,
                    'params': params or {}}
    request = json.dumps(request_data)
    response = json.loads(unicode(xbmc.executeJSONRPC(request), 'utf-8',
                                  errors='ignore'))
    if 'error' in response:
        raise IOError('JSONRPC-Error {}: {}'
                      .format(response['error']['code'],
                              response['error']['message']))
    return response['result']


def update_library_item_details(dbtype, dbid, details):
    """
    Update properties of an item in the Kodi library
    """
    method = 'VideoLibrary.Set{}Details'.format(dbtype.capitalize())
    params = {'{}id'.format(dbtype): dbid}
    params.update(details)
    return json_rpc(method, params)


def retry(func, max_tries, sleep_time=3000):
    """
    Retry an operation max_tries times and wait sleep_time milliseconds
    inbetween. Silently ignores exceptions.
    """
    for _ in range(1, max_tries):
        try:
            result = func()
            if result is not None:
                return result
        # pylint: disable=bare-except
        except:
            pass
        xbmc.sleep(sleep_time)
    return None


def get_active_video_player():
    """
    Return the id of the currently active Kodi video player or None
    if there's no active player.
    """
    return next((player['playerid']
                 for player in json_rpc('Player.GetActivePlayers')
                 if player['type'] == 'video'),
                None)


def find_episode(episode_id, seasons):
    """
    Return metadata for a specific episode from within a nested
    metadata dict.
    Returns an empty dict if the episode could not be found.
    """
    episodes = (e for season_episodes in (s['episodes'] for s in seasons)
                for e in season_episodes)
    return next((episode
                 for episode in episodes
                 if str(episode['id']) == episode_id),
                {})
