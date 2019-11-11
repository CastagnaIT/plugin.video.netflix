# -*- coding: utf-8 -*-
"""Common exception types for API operations"""
from __future__ import absolute_import, division, unicode_literals


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


class InvalidProfilesError(WebsiteParsingError):
    """Cannot extract profiles from Netflix webpage"""


class InvalidMembershipStatusError(WebsiteParsingError):
    """The user logging in does not have a valid subscription"""


class LoginFailedError(Exception):
    """The login attempt has failed"""


class LoginValidateError(Exception):
    """The login validate has generated an error"""


class NotLoggedInError(Exception):
    """The requested operation requires a valid and active login, which
    is not present"""


class APIError(Exception):
    """The requested API operation has resulted in an error"""
