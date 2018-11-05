# -*- coding: utf-8 -*-
"""Persistent cookie management"""
from __future__ import unicode_literals

import os
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
    pass


class CookiesExpiredError(Exception):
    """Stored cookies are expired"""
    pass


def save(account_hash, cookie_jar):
    """Save a cookie jar to file and in-memory storage"""
    # pylint: disable=broad-except
    g.COOKIES[account_hash] = cookie_jar
    cookie_file = xbmcvfs.File(cookie_filename(account_hash), 'w')
    try:
        pickle.dump(cookie_jar, cookie_file)
    except Exception as exc:
        common.error('Failed to save cookies to file: {exc}', exc)
    finally:
        cookie_file.close()


def delete(account_hash):
    """Delete cookies for an account from in-memory storage and the disk"""
    # pylint: disable=broad-except
    del g.COOKIES[account_hash]
    try:
        xbmcvfs.delete(cookie_filename(account_hash))
    except Exception as exc:
        common.error('Failed to delete cookies on disk: {exc}', exc)


def load(account_hash):
    """Load cookies for a given account and check them for validity"""
    cookie_jar = (g.COOKIES.get(account_hash) or
                  load_from_file(account_hash))

    if expired(cookie_jar):
        raise CookiesExpiredError()

    g.COOKIES[account_hash] = cookie_jar

    return cookie_jar


def load_from_file(account_hash):
    """Load cookies for a given account from file"""
    common.debug('Loading cookies from file')
    cookie_file = xbmcvfs.File(cookie_filename(account_hash), 'r')
    try:
        return pickle.load(cookie_file)
    except Exception as exc:
        common.error('Failed to load cookies from file: {exc}', exc)
        raise MissingCookiesError()
    finally:
        cookie_file.close()


def expired(cookie_jar):
    """Check if one of the cookies in the jar is already expired"""
    earliest_expiration = 99999999999999999999
    for cookie in cookie_jar:
        if (cookie.expires is not None and
                int(cookie.expires) < earliest_expiration):
            earliest_expiration = int(cookie.expires)
    return int(time()) > earliest_expiration


def cookie_filename(account_hash):
    """Return a filename to store cookies for a given account"""
    return xbmc.translatePath('{}_{}'.format(g.COOKIE_PATH, account_hash))
