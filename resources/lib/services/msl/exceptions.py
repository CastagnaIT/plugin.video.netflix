# -*- coding: utf-8 -*-
"""Common MSL exceptions"""
from __future__ import unicode_literals


class MSLError(Exception):
    pass


class LicenseError(MSLError):
    pass


class ManifestError(MSLError):
    pass


class MastertokenExpired(MSLError):
    pass
