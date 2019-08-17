# -*- coding: utf-8 -*-
"""Functions to create new databases"""
from __future__ import unicode_literals

import os
import sqlite3 as sql

from resources.lib.globals import g

import resources.lib.common as common
import resources.lib.database.db_utils as db_utils

# TODO: In the future, when the databases are stable, we can create the sql code for db creation
# TODO: And so removing the db file copy


def check_database_file(db_filename):
    """If database file do not exist copy a new one from addon folder"""
    if common.file_exists(db_filename, os.path.join(g.ADDON_DATA_PATH, 'database'))\
       and not common.file_exists(db_filename, os.path.join(g.DATA_PATH, 'database')):
        common.debug('Database file {} is missing, copy a new one'.format(db_filename))

        common.copy_file(os.path.join(g.ADDON_DATA_PATH, 'database', db_filename),
                         os.path.join(g.DATA_PATH, 'database', db_filename))


def create_database(db_file_path):
    if db_utils.LOCAL_DB_FILENAME in db_file_path:
        _create_local_database(db_file_path)
    if db_utils.SHARED_DB_FILENAME in db_file_path:
        _create_shared_database(db_file_path)


def _create_local_database(db_file_path):
    """Create a new local database"""
    pass


def _create_shared_database(db_file_path):
    """Create a new shared database"""
    pass
