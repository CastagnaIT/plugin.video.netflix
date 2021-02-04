# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Persistent cookie management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import pickle
from time import time

import xbmcvfs

from resources.lib.common.exceptions import MissingCookiesError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


def save(cookie_jar, log_output=True):
    """Save a cookie jar to file and in-memory storage"""
    if log_output:
        log_cookie(cookie_jar)
    cookie_file = xbmcvfs.File(cookie_file_path(), 'wb')
    try:
        # pickle.dump(cookie_jar, cookie_file)
        cookie_file.write(bytearray(pickle.dumps(cookie_jar)))
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('Failed to save cookies to file: {exc}', exc=exc)
    finally:
        cookie_file.close()


def delete():
    """Delete cookies for an account from the disk"""
    try:
        xbmcvfs.delete(cookie_file_path())
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('Failed to delete cookies on disk: {exc}', exc=exc)


def load():
    """Load cookies for a given account and check them for validity"""
    file_path = cookie_file_path()
    if not xbmcvfs.exists(file_path):
        LOG.debug('Cookies file does not exist')
        raise MissingCookiesError
    LOG.debug('Loading cookies from {}', file_path)
    cookie_file = xbmcvfs.File(file_path, 'rb')
    try:
        cookie_jar = pickle.loads(cookie_file.readBytes())
        # Clear flwssn cookie if present, as it is trouble with early expiration
        if 'flwssn' in cookie_jar:
            cookie_jar.clear(domain='.netflix.com', path='/', name='flwssn')
        log_cookie(cookie_jar)
        return cookie_jar
    except Exception as exc:  # pylint: disable=broad-except
        import traceback
        LOG.error('Failed to load cookies from file: {exc}', exc=exc)
        LOG.error(traceback.format_exc())
        raise MissingCookiesError from exc
    finally:
        cookie_file.close()


def log_cookie(cookie_jar):
    """Print cookie info to the log"""
    if not LOG.is_enabled:
        return
    debug_output = 'Cookies currently loaded:\n'
    for cookie in cookie_jar:
        remaining_ttl = int((cookie.expires or 0) - time()) if cookie.expires else None
        debug_output += '{} (expires ts {} - remaining TTL {} sec)\n'.format(cookie.name,
                                                                             cookie.expires,
                                                                             remaining_ttl)
    LOG.debug(debug_output)


def cookie_file_path():
    """Return the file path to store cookies"""
    return xbmcvfs.translatePath(G.COOKIES_PATH)


def convert_chrome_cookie(cookie):
    """Convert a cookie from Chrome to a CookieJar format type"""
    kwargs = {'domain': cookie['domain']}
    if cookie['expires'] != -1:
        kwargs['expires'] = int(cookie['expires'])
    kwargs['path'] = cookie['path']
    kwargs['secure'] = cookie['secure']
    if cookie['httpOnly']:
        kwargs['rest'] = {'HttpOnly': True}
    return cookie['name'], cookie['value'], kwargs
