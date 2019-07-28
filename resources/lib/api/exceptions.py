# -*- coding: utf-8 -*-
"""Common exception types for API operations"""
from __future__ import unicode_literals


class MissingCredentialsError(Exception):
    """There are no stored credentials to load"""
    pass


class InvalidReferenceError(Exception):
    """The provided reference cannot be dealt with as it is in an
    unexpected format"""
    pass


class InvalidVideoListTypeError(Exception):
    """No video list of a given was available"""
    pass


class WebsiteParsingError(Exception):
    """Parsing info from the Netflix Website failed"""
    pass


class InvalidAuthURLError(WebsiteParsingError):
    """The authURL is invalid"""
    pass


class InvalidProfilesError(WebsiteParsingError):
    """Cannot extract profiles from Netflix webpage"""
    pass


class InvalidMembershipStatusError(WebsiteParsingError):
    """The user logging in does not have a valid subscription"""
    pass


class LoginFailedError(Exception):
    """The login attempt has failed"""
    pass


class LoginValidateError(Exception):
    """The login validate has generated an error"""
    pass


class NotLoggedInError(Exception):
    """The requested operation requires a valid and active login, which
    is not present"""
    pass


class APIError(Exception):
    """The requested API operation has resulted in an error"""
    pass
