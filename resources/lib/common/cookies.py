# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Persistent cookie management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from time import time
try:
    import cPickle as pickle
except ImportError:
    import pickle

import xbmc
import xbmcvfs

from resources.lib.globals import g
import resources.lib.common as common


class MissingCookiesError(Exception):
    """No session cookies have been stored"""


class CookiesExpiredError(Exception):
    """Stored cookies are expired"""


def save(account_hash, cookie_jar):
    """Save a cookie jar to file and in-memory storage"""
    # pylint: disable=broad-except
    g.COOKIES[account_hash] = cookie_jar
    cookie_file = xbmcvfs.File(cookie_filename(account_hash), 'wb')
    try:
        # pickle.dump(cookie_jar, cookie_file)
        cookie_file.write(bytearray(pickle.dumps(cookie_jar)))
    except Exception as exc:
        common.error('Failed to save cookies to file: {exc}', exc=exc)
    finally:
        cookie_file.close()


def delete(account_hash):
    """Delete cookies for an account from in-memory storage and the disk"""
    # pylint: disable=broad-except
    if g.COOKIES.get(account_hash):
        del g.COOKIES[account_hash]
    try:
        xbmcvfs.delete(cookie_filename(account_hash))
    except Exception as exc:
        common.error('Failed to delete cookies on disk: {exc}', exc=exc)


def load(account_hash):
    """Load cookies for a given account and check them for validity"""
    filename = cookie_filename(account_hash)
    common.debug('Loading cookies from {}', filename)
    if not xbmcvfs.exists(xbmc.translatePath(filename)):
        common.debug('Cookies file does not exist')
        raise MissingCookiesError()
    try:
        cookie_file = xbmcvfs.File(filename, 'rb')
        if g.PY_IS_VER2:
            # pickle.loads on py2 wants string
            cookie_jar = pickle.loads(cookie_file.read())
        else:
            cookie_jar = pickle.loads(cookie_file.readBytes())
    except Exception as exc:
        import traceback
        common.error('Failed to load cookies from file: {exc}', exc=exc)
        common.error(traceback.format_exc())
        raise MissingCookiesError()
    finally:
        cookie_file.close()
    # Clear flwssn cookie if present, as it is trouble with early expiration
    try:
        cookie_jar.clear(domain='.netflix.com', path='/', name='flwssn')
    except KeyError:
        pass

    debug_output = 'Loaded cookies:\n'
    for cookie in cookie_jar:
        remaining_ttl = ((cookie.expires or 0) - time() / 60) if cookie.expires else None
        debug_output += '{} (expires {} - remaining TTL {})\n'.format(cookie.name,
                                                                      cookie.expires,
                                                                      remaining_ttl)
    # if expired(cookie_jar):
    #     raise CookiesExpiredError()
    return cookie_jar


def expired(cookie_jar):
    """Check if one of the cookies in the jar is already expired"""
    earliest_expiration = 99999999999999999999
    for cookie in cookie_jar:
        if cookie.expires is not None:
            earliest_expiration = min(int(cookie.expires), earliest_expiration)
    return int(time()) > earliest_expiration


def cookie_filename(account_hash):
    """Return a filename to store cookies for a given account"""
    return xbmc.translatePath('{}_{}'.format(g.COOKIE_PATH, account_hash))
