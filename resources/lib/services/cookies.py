# -*- coding: utf-8 -*-
"""Persistent cookie management"""
from __future__ import unicode_literals

import os
from time import time
try:
    import cPickle as pickle
except ImportError:
    import pickle

import resources.lib.common as common

COOKIES = {}
"""In-memory storage for account cookies"""

class MissingCookiesError(Exception):
    """No session cookies have been stored"""
    pass

class CookiesExpiredError(Exception):
    """Stored cookies are expired"""
    pass

def save(account_hash, cookie_jar):
    """Save a cookie jar to file and in-memory storage"""
    # pylint: disable=broad-except
    COOKIES[account_hash] = cookie_jar
    try:
        with open(cookie_filename(account_hash), 'wb') as cookie_file:
            common.debug('Saving cookies to file')
            pickle.dump(cookie_jar, cookie_file)
    except Exception as exc:
        common.error('Failed to save cookies to file: {exc}', exc)

def delete(account_hash):
    """Delete cookies for an account from in-memory storage and the disk"""
    # pylint: disable=broad-except
    del COOKIES[account_hash]
    try:
        os.remove(cookie_filename(account_hash))
    except Exception as exc:
        common.error('Failed to delete cookies on disk: {exc}', exc)

def load(account_hash):
    """Load cookies for a given account and check them for validity"""
    cookie_jar = (COOKIES.get(account_hash) or
                  load_from_file(account_hash))

    if expired(cookie_jar):
        raise CookiesExpiredError()

    COOKIES[account_hash] = cookie_jar

    return cookie_jar

def load_from_file(account_hash):
    """Load cookies for a given account from file"""
    try:
        with open(cookie_filename(account_hash), 'rb') as cookie_file:
            common.debug('Loading cookies from file')
            return pickle.load(cookie_file)
    except Exception as exc:
        common.error('Failed to load cookies from file: {exc}', exc)
        raise MissingCookiesError()

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
    return '{}_{}'.format(common.COOKIE_PATH, account_hash)
