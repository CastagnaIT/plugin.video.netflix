# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Miscellaneous database utility functions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os

import xbmcvfs

from resources.lib.globals import G


LOCAL_DB_FILENAME = 'nf_local.sqlite3'
SHARED_DB_FILENAME = 'nf_shared.sqlite3'

# Table mapping: ( Table name, [ columns ] )
TABLE_APP_CONF = ('app_config', ['Name', 'Value'])
TABLE_SESSION = ('session', ['Name', 'Value'])
TABLE_MENU_DATA = ('menu_data', ['ContextId', 'Value'])
TABLE_SETTINGS_MONITOR = ('settings_monitor', ['Name', 'Value'])
TABLE_SHARED_APP_CONF = ('shared_app_config', ['Name', 'Value'])


# Mapping the video library columns of the tables
VidLibProp = {
    'exclude_update': 'ExcludeUpdate',
    'nfo_export': 'NfoExport',
    'file_path': 'FilePath'
}


def get_local_db_path(db_filename):
    # First ensure database folder exists
    from resources.lib.common import folder_exists
    db_folder = xbmcvfs.translatePath(os.path.join(G.DATA_PATH, 'database'))
    if not folder_exists(db_folder):
        xbmcvfs.mkdirs(db_folder)
    return os.path.join(db_folder, db_filename)


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
    columns_to_set = ', '.join(set_columns)
    where_columns = [col + ' = ?' for col in where_columns]
    where_condition = ' AND '.join(where_columns)
    query = f'UPDATE {table} SET {columns_to_set} WHERE {where_condition}'
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
    query_columns = ', '.join(set_columns)
    values_fields = ', '.join(values_fields)
    query = f'INSERT INTO {table} ({query_columns}) VALUES ({values_fields})'
    return query, values


def mysql_insert_or_update(table, id_columns, columns):
    """
    Create a MySQL insert or update query (required multi=True)
    """
    columns[0:0] = id_columns
    sets_columns = [f'@{col}' for col in columns]
    sets = [f'{col} = %s' for col in sets_columns]
    query_set = f'SET {", ".join(sets)};'
    query_columns = ', '.join(columns)
    values = ', '.join(sets_columns)
    query_insert = f'INSERT INTO {table} ({query_columns}) VALUES ({values})'

    columns = list(set(columns) - set(id_columns))  # Fastest method to remove list to list tested
    on_duplicate_params = [f'{col} = @{col}' for col in columns]
    query_duplicate = f'ON DUPLICATE KEY UPDATE {", ".join(on_duplicate_params)};'
    return ' '.join([query_set, query_insert, query_duplicate])
