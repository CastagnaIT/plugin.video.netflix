# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Persistent cookie management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import pickle
from http.cookiejar import CookieJar
from threading import RLock
from time import time

import xbmcvfs

from resources.lib.common.exceptions import MissingCookiesError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG


class PickleableCookieJar(CookieJar):
    """A pickleable CookieJar class"""
    # This code has been adapted from RequestsCookieJar of "Requests" module
    @classmethod
    def cast(cls, cookie_jar: CookieJar):
        """Make a kind of cast to convert the class from CookieJar to PickleableCookieJar"""
        assert isinstance(cookie_jar, CookieJar)
        cookie_jar.__class__ = cls
        assert isinstance(cookie_jar, PickleableCookieJar)
        return cookie_jar

    def __getstate__(self):
        """Unlike a normal CookieJar, this class is pickleable."""
        state = self.__dict__.copy()
        # remove the unpickleable RLock object
        state.pop('_cookies_lock')
        return state

    def __setstate__(self, state):
        """Unlike a normal CookieJar, this class is pickleable."""
        self.__dict__.update(state)
        if '_cookies_lock' not in self.__dict__:
            self._cookies_lock = RLock()


def save(cookie_jar, log_output=True):
    """Save a cookie jar to file and in-memory storage"""
    if log_output:
        log_cookie(cookie_jar)
    cookie_file = xbmcvfs.File(cookie_file_path(), 'wb')
    try:
        cookie_file.write(bytearray(pickle.dumps(PickleableCookieJar.cast(cookie_jar))))
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
        debug_output += f'{cookie.name} (expires ts {cookie.expires} - remaining TTL {remaining_ttl} sec)\n'
    LOG.debug(debug_output)


def cookie_file_path():
    """Return the file path to store cookies"""
    return xbmcvfs.translatePath(G.COOKIES_PATH)


def convert_chrome_cookie(cookie):
    """Convert a cookie from Chrome to a CookieJar format type"""
    return {
        'name': cookie['name'],
        'value': cookie['value'],
        'domain': cookie['domain'],
        'path': cookie['path'],
        'secure': cookie['secure'],
        'expires': int(cookie['expires']) if cookie['expires'] != -1 else None,
        'rest': {'HttpOnly': True if cookie['httpOnly'] else None}
    }
