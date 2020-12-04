# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Specific exceptions types

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
# Note: This module is also used to dynamically raise exceptions for IPC (see _raise_for_error in ipc.py)


# Exceptions for API's / DATA PROCESSING / WEB DATA PROCESSING

class APIError(Exception):
    """The requested API operation has resulted in an error"""


class HttpError401(Exception):
    """The request has returned http error 401 unauthorized for url ..."""


class HttpErrorTimeout(Exception):
    """The request has raised timeout"""


class WebsiteParsingError(Exception):
    """Parsing info from the Netflix Website failed"""


class MissingCookiesError(Exception):
    """No session cookies have been stored"""


class InvalidAuthURLError(WebsiteParsingError):
    """The authURL is not valid"""


class InvalidReferenceError(Exception):
    """The provided reference cannot be dealt with as it is in an unexpected format"""


class InvalidVideoListTypeError(Exception):
    """No video list of a given was available"""


class InvalidProfilesError(Exception):
    """Cannot get profiles data from Netflix"""


class InvalidVideoId(Exception):
    """The provided video id is not valid"""


class MetadataNotAvailable(Exception):
    """Metadata not found"""


# Exceptions for MSL specific

class MSLError(Exception):
    """A specific MSL error"""
    def __init__(self, message, err_number=None):
        self.message = message
        self.err_number = err_number
        super(MSLError, self).__init__(self.message)


class LicenseError(MSLError):
    """License processing error"""


class ManifestError(MSLError):
    """Manifest processing error"""


# Exceptions for ACCOUNT / LOGIN

class MissingCredentialsError(Exception):
    """There are no stored credentials to load"""


class LoginError(Exception):
    """The login has failed"""


class LoginValidateError(Exception):
    """The login request has failed for a specified reason"""


class NotLoggedInError(Exception):
    """A check has determined the non-logged status"""


class MbrStatusError(Exception):
    """Membership status error: The user logging in does not have a valid subscription"""


class MbrStatusAnonymousError(Exception):
    """
    Membership status error: The user logging failed --mainly-- for:
    password changed / expired cookies / request to disconnect devices
    there may also be other unknown cases
    """


class MbrStatusNeverMemberError(Exception):
    """Membership status error: The user logging failed because of account not been confirmed"""


class MbrStatusFormerMemberError(Exception):
    """Membership status error: The user logging failed because of account not been reactivated"""


# Exceptions for DATABASE

class DBSQLiteConnectionError(Exception):
    """An error occurred in the database connection"""


class DBSQLiteError(Exception):
    """An error occurred in the database operations"""


class DBMySQLConnectionError(Exception):
    """An error occurred in the database connection"""


class DBMySQLError(Exception):
    """An error occurred in the database operations"""


class DBProfilesMissing(Exception):
    """There are no stored profiles in database"""


# All other exceptions

class InvalidPathError(Exception):
    """The requested path is invalid and could not be routed"""


class BackendNotReady(Exception):
    """The background services are not started yet"""


class NotConnected(Exception):
    """Internet status not connected"""


class CacheMiss(Exception):
    """The Requested item is not in the cache"""


class UnknownCacheBucketError(Exception):
    """The requested cache bucket does not exist"""


class ItemNotFound(Exception):
    """The requested item could not be found in the Kodi library"""


class InputStreamHelperError(Exception):
    """An internal error has occurred to InputStream Helper add-on"""
