# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Common exception types for API operations

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals
# Note: This module is used to dynamically generate return exceptions for IPC Http (see _raise_for_error in ipc.py)


class InvalidPathError(Exception):
    """The requested path is invalid and could not be routed"""


class MissingCredentialsError(Exception):
    """There are no stored credentials to load"""


class InvalidReferenceError(Exception):
    """The provided reference cannot be dealt with as it is in an
    unexpected format"""


class InvalidVideoListTypeError(Exception):
    """No video list of a given was available"""


class WebsiteParsingError(Exception):
    """Parsing info from the Netflix Website failed"""


class InvalidAuthURLError(WebsiteParsingError):
    """The authURL is invalid"""


class InvalidProfilesError(Exception):
    """Cannot get profiles data from Netflix"""


class InvalidMembershipStatusError(WebsiteParsingError):
    """The user logging in does not have a valid subscription"""


class InvalidMembershipStatusAnonymous(WebsiteParsingError):
    """The user logging failed because of Membership Status Anonymous"""


class LoginFailedError(Exception):
    """The login attempt has failed"""


class LoginValidateError(Exception):
    """The login validate has generated an error"""


class LoginValidateErrorIncorrectPassword(Exception):
    """The login validate has generated incorrect password error"""


class NotLoggedInError(Exception):
    """The requested operation requires a valid and active login, which
    is not present"""


class APIError(Exception):
    """The requested API operation has resulted in an error"""


class NotConnected(Exception):
    """Internet status not connected"""


class MetadataNotAvailable(Exception):
    """Metadata not found"""


class CacheMiss(Exception):
    """The Requested item is not in the cache"""


class UnknownCacheBucketError(Exception):
    """The requested cache bucket does not exist"""


class HttpError401(Exception):
    """The request has returned http error 401 unauthorized for url ..."""


class InputStreamHelperError(Exception):
    """An internal error has occurred to InputStream Helper add-on"""
