# -*- coding: utf-8 -*-
"""Miscellaneous database utility functions"""
from __future__ import unicode_literals

import os
import xbmc
import resources.lib.common as common

from enum import Enum
from resources.lib.globals import g


LOCAL_DB_FILENAME = 'nf_local.sqlite3'
SHARED_DB_FILENAME = 'nf_shared.sqlite3'

# Table mapping: ( Table name, [ columns ] )
TABLE_APP_CONF = ('app_config', ['Name', 'Value'])
TABLE_SESSION = ('session', ['Name', 'Value'])
TABLE_MENU_DATA = ('menu_data', ['ContextId', 'Value'])
TABLE_SETTINGS_MONITOR = ('settings_monitor', ['Name', 'Value'])
TABLE_SHARED_APP_CONF = ('shared_app_config', ['Name', 'Value'])


# Enum mapping the video library columns of the tables
class VidLibProp(Enum):
    exclude_update = 'ExcludeUpdate'
    nfo_export = 'NfoExport'
    file_path = 'FilePath'


def get_local_db_path(db_filename):
    return xbmc.translatePath(os.path.join(g.DATA_PATH, 'database', db_filename))


def sql_filtered_update(table, set_columns, where_columns, values):
    """
    Generates dynamically a sql update query by eliminating the columns that have value to None
    WARNING: RESPECT columns AND values SORT ORDER IN THE LISTS!
    If the values are positioned incorrectly with respect to the column names,
    they will be saved in the wrong column!
    """
    for index in range(len(set_columns) - 1, -1, -1):
        if values[index] is None:
            del set_columns[index]
            del values[index]
    set_columns = [col + ' = ?' for col in set_columns]
    where_columns = [col + ' = ?' for col in where_columns]
    query = 'UPDATE {} SET {} WHERE {}'.format(
        table,
        ', '.join(set_columns),
        ' AND '.join(where_columns)
    )
    return query, values


def sql_filtered_insert(table, set_columns, values):
    """
    Generates dynamically a sql insert query by eliminating the columns that have value to None
    WARNING: RESPECT columns AND values SORT ORDER IN THE LISTS!
    If the values are positioned incorrectly with respect to the column names,
    they will be saved in the wrong column!
    """
    for index in range(len(set_columns) - 1, -1, -1):
        if values[index] is None:
            del set_columns[index]
            del values[index]
    values_fields = ['?'] * len(set_columns)
    query = 'INSERT INTO {} ({}) VALUES ({})'.format(
        table,
        ', '.join(set_columns),
        ', '.join(values_fields)
    )
    return query, values


def mysql_insert_or_update(table, id_columns, columns):
    """
    Create a MySQL insert or update query (required multi=True)
    """
    columns[0:0] = id_columns
    sets_columns = ['@' + col for col in columns]
    sets = [col + ' = %s' for col in sets_columns]
    query_set = 'SET {};'.format(', '.join(sets))
    query_insert = 'INSERT INTO {} ({}) VALUES ({})'.format(table,
                                                            ', '.join(columns),
                                                            ', '.join(sets_columns))
    columns = list(set(columns)-set(id_columns))  # Fastest method to remove list to list tested
    on_duplicate_params = [col + ' = @' + col for col in columns]
    query_duplicate = 'ON DUPLICATE KEY UPDATE {}'.format(', '.join(on_duplicate_params)) + ';'
    return ' '.join([query_set, query_insert, query_duplicate])
