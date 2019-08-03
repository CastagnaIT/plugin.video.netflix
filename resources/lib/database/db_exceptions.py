# -*- coding: utf-8 -*-
"""Common exception types for database operations"""
from __future__ import unicode_literals


class SQLConnectionError(Exception):
    """An error occurred in the database connection"""
    pass


class SQLError(Exception):
    """An error occurred in the database operations"""
    pass


class ProfilesMissing(Exception):
    """There are no stored profiles in database"""
    pass
