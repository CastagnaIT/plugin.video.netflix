# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Functions to create a new SQLite database

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import sqlite3 as sql

import resources.lib.database.db_utils as db_utils
from resources.lib.utils.logging import LOG


def create_database(db_file_path, db_filename):
    LOG.debug('The SQLite database {} is empty, creating tables', db_filename)
    if db_utils.LOCAL_DB_FILENAME == db_filename:
        _create_local_database(db_file_path)
    if db_utils.SHARED_DB_FILENAME == db_filename:
        _create_shared_database(db_file_path)


def _create_local_database(db_file_path):
    """Create a new local database"""
    conn = sql.connect(db_file_path)
    cur = conn.cursor()

    table = str('CREATE TABLE app_config ('
                'ID    INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,'
                'Name  TEXT    UNIQUE NOT NULL,'
                'Value TEXT);')
    cur.execute(table)

    table = str('CREATE TABLE menu_data ('
                'ContextId TEXT PRIMARY KEY NOT NULL,'
                'Value     TEXT);')
    cur.execute(table)

    table = str('CREATE TABLE profiles ('
                'ID        INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,'
                'Guid      TEXT    NOT NULL UNIQUE,'
                'IsActive  BOOLEAN DEFAULT (0) NOT NULL,'
                'SortOrder INTEGER NOT NULL);')
    cur.execute(table)

    table = str('CREATE TABLE profiles_config ('
                'Guid  TEXT NOT NULL,'
                'Name  TEXT NOT NULL,'
                'Value TEXT,'
                'PRIMARY KEY (Guid, Name ),'
                'FOREIGN KEY (Guid)'
                'REFERENCES Profiles (Guid) ON DELETE CASCADE ON UPDATE CASCADE);')
    cur.execute(table)

    table = str('CREATE TABLE session ('
                'Name  TEXT PRIMARY KEY NOT NULL,'
                'Value TEXT);')
    cur.execute(table)

    table = str('CREATE TABLE settings_monitor ('
                'Name  TEXT PRIMARY KEY NOT NULL,'
                'Value TEXT);')
    cur.execute(table)

    table = str('CREATE TABLE search ('
                'ID         INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,'
                'Guid       TEXT    NOT NULL REFERENCES profiles (Guid) ON DELETE CASCADE ON UPDATE CASCADE,'
                'Type       TEXT    NOT NULL,'
                'Value      TEXT    NOT NULL,'
                'Parameters TEXT,'
                'LastAccess TEXT);')
    cur.execute(table)

    if conn:
        conn.close()


def _create_shared_database(db_file_path):
    """Create a new shared database"""
    conn = sql.connect(db_file_path)
    cur = conn.cursor()

    table = str('CREATE TABLE profiles ('
                'ID        INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,'
                'Guid      TEXT    NOT NULL UNIQUE,'
                'SortOrder INTEGER NOT NULL);')
    cur.execute(table)

    table = str('CREATE TABLE shared_app_config ('
                'ID    INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,'
                'Name  TEXT    NOT NULL UNIQUE,'
                'Value TEXT);')
    cur.execute(table)

    table = str('CREATE TABLE stream_continuity ('
                'ProfileGuid      TEXT    NOT NULL,'
                'VideoID          INTEGER NOT NULL,'
                'Value            TEXT,'
                'DateLastModified TEXT    NOT NULL,'
                'PRIMARY KEY (ProfileGuid, VideoID ),'
                'FOREIGN KEY (ProfileGuid)'
                'REFERENCES Profiles (Guid) ON DELETE CASCADE ON UPDATE CASCADE);')
    cur.execute(table)

    table = str('CREATE TABLE video_lib_episodes ('
                'EpisodeID INTEGER,'
                'SeasonID  INTEGER,'
                'FilePath  TEXT,'
                'PRIMARY KEY (EpisodeID, SeasonID));')
    cur.execute(table)

    table = str('CREATE TABLE video_lib_movies ('
                'MovieID   INTEGER PRIMARY KEY NOT NULL,'
                'FilePath  TEXT    NOT NULL,'
                'NfoExport TEXT    NOT NULL DEFAULT (\'False\'));')
    cur.execute(table)

    table = str('CREATE TABLE video_lib_seasons ('
                'TvShowID INTEGER NOT NULL,'
                'SeasonID INTEGER NOT NULL,'
                'PRIMARY KEY (TvShowID, SeasonID));')
    cur.execute(table)

    table = str('CREATE TABLE video_lib_tvshows ('
                'TvShowID      INTEGER PRIMARY KEY NOT NULL,'
                'ExcludeUpdate TEXT    NOT NULL DEFAULT (\'False\'),'
                'NfoExport     TEXT    NOT NULL DEFAULT (\'False\'));')
    cur.execute(table)

    table = str('CREATE TABLE watched_status_override ('
                'ProfileGuid      TEXT    NOT NULL,'
                'VideoID          INTEGER NOT NULL,'
                'Value            TEXT,'
                'PRIMARY KEY (ProfileGuid, VideoID ),'
                'FOREIGN KEY (ProfileGuid)'
                'REFERENCES Profiles (Guid) ON DELETE CASCADE ON UPDATE CASCADE);')
    cur.execute(table)

    if conn:
        conn.close()
