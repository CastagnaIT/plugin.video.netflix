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

import xbmc
import xbmcvfs

from resources.lib.common.exceptions import MissingCookiesError
from resources.lib.globals import G
from resources.lib.utils.logging import LOG

try:
    import cPickle as pickle
except ImportError:
    import pickle


def save(account_hash, cookie_jar, log_output=True):
    """Save a cookie jar to file and in-memory storage"""
    if log_output:
        log_cookie(cookie_jar)
    cookie_file = xbmcvfs.File(cookie_filename(account_hash), 'wb')
    try:
        # pickle.dump(cookie_jar, cookie_file)
        cookie_file.write(bytearray(pickle.dumps(cookie_jar)))
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('Failed to save cookies to file: {exc}', exc=exc)
    finally:
        cookie_file.close()


def delete(account_hash):
    """Delete cookies for an account from the disk"""
    try:
        xbmcvfs.delete(cookie_filename(account_hash))
    except Exception as exc:  # pylint: disable=broad-except
        LOG.error('Failed to delete cookies on disk: {exc}', exc=exc)


def load(account_hash):
    """Load cookies for a given account and check them for validity"""
    filename = cookie_filename(account_hash)
    if not xbmcvfs.exists(filename):
        LOG.debug('Cookies file does not exist')
        raise MissingCookiesError
    LOG.debug('Loading cookies from {}', G.py2_decode(filename))
    cookie_file = xbmcvfs.File(filename, 'rb')
    try:
        if G.PY_IS_VER2:
            # pickle.loads on py2 wants string
            cookie_jar = pickle.loads(cookie_file.read())
        else:
            cookie_jar = pickle.loads(cookie_file.readBytes())
    except Exception as exc:  # pylint: disable=broad-except
        import traceback
        LOG.error('Failed to load cookies from file: {exc}', exc=exc)
        LOG.error(G.py2_decode(traceback.format_exc(), 'latin-1'))
        raise MissingCookiesError
    finally:
        cookie_file.close()
    # Clear flwssn cookie if present, as it is trouble with early expiration
    if 'flwssn' in cookie_jar:
        cookie_jar.clear(domain='.netflix.com', path='/', name='flwssn')
    log_cookie(cookie_jar)
    return cookie_jar


def log_cookie(cookie_jar):
    """Print cookie info to the log"""
    if not LOG.level == LOG.LEVEL_VERBOSE:
        return
    debug_output = 'Cookies currently loaded:\n'
    for cookie in cookie_jar:
        remaining_ttl = int((cookie.expires or 0) - time()) if cookie.expires else None
        debug_output += '{} (expires ts {} - remaining TTL {} sec)\n'.format(cookie.name,
                                                                             cookie.expires,
                                                                             remaining_ttl)
    LOG.debug(debug_output)


def cookie_filename(account_hash):
    """Return a filename to store cookies for a given account"""
    return xbmc.translatePath('{}_{}'.format(G.COOKIE_PATH, account_hash))
