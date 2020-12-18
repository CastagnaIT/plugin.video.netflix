# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Functions to create a new MySQL database

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import mysql.connector

from resources.lib.utils.logging import LOG


def create_database(config):
    """Create a new database"""
    db_name = config.pop('database', None)
    LOG.debug('The MySQL database {} does not exist, creating a new one', db_name)
    conn = mysql.connector.connect(**config)
    cur = conn.cursor()

    schema = ('CREATE DATABASE netflix_addon '
              'CHARACTER SET utf8mb4 '
              'COLLATE utf8mb4_unicode_ci;')
    cur.execute(schema)

    table = ('CREATE TABLE netflix_addon.profiles ('
             'ID INT(11) NOT NULL AUTO_INCREMENT,'
             'Guid VARCHAR(50) NOT NULL,'
             'SortOrder INT(11) NOT NULL,'
             'PRIMARY KEY (ID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    alter_tbl = ('ALTER TABLE netflix_addon.profiles '
                 'ADD UNIQUE INDEX Guid(Guid);')
    cur.execute(table)
    cur.execute(alter_tbl)

    table = ('CREATE TABLE netflix_addon.shared_app_config ('
             'ID INT(11) NOT NULL AUTO_INCREMENT,'
             'Name VARCHAR(100) NOT NULL,'
             'Value TEXT DEFAULT NULL,'
             'PRIMARY KEY (ID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    alter_tbl = ('ALTER TABLE netflix_addon.shared_app_config '
                 'ADD UNIQUE INDEX Name_UNIQUE(Name);')
    cur.execute(table)
    cur.execute(alter_tbl)

    table = ('CREATE TABLE netflix_addon.stream_continuity ('
             'ProfileGuid VARCHAR(50) NOT NULL,'
             'VideoID INT(11) NOT NULL,'
             'Value TEXT DEFAULT NULL,'
             'DateLastModified VARCHAR(50) NOT NULL,'
             'PRIMARY KEY (ProfileGuid, VideoID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    alter_tbl = ('ALTER TABLE netflix_addon.stream_continuity '
                 'ADD CONSTRAINT FK_streamcontinuity_ProfileGuid FOREIGN KEY (ProfileGuid)'
                 'REFERENCES netflix_addon.profiles(Guid) ON DELETE CASCADE ON UPDATE CASCADE;')
    cur.execute(table)
    cur.execute(alter_tbl)

    table = ('CREATE TABLE netflix_addon.video_lib_episodes ('
             'EpisodeID INT(11) NOT NULL,'
             'SeasonID INT(11) NOT NULL,'
             'FilePath TEXT DEFAULT NULL,'
             'PRIMARY KEY (EpisodeID, SeasonID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    cur.execute(table)

    table = ('CREATE TABLE netflix_addon.video_lib_movies ('
             'MovieID INT(11) NOT NULL,'
             'FilePath TEXT DEFAULT NULL,'
             'NfoExport VARCHAR(5) NOT NULL DEFAULT \'False\','
             'PRIMARY KEY (MovieID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    cur.execute(table)

    table = ('CREATE TABLE netflix_addon.video_lib_seasons ('
             'TvShowID INT(11) NOT NULL,'
             'SeasonID INT(11) NOT NULL,'
             'PRIMARY KEY (TvShowID, SeasonID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    cur.execute(table)

    table = ('CREATE TABLE netflix_addon.video_lib_tvshows ('
             'TvShowID INT(11) NOT NULL,'
             'ExcludeUpdate VARCHAR(5) NOT NULL DEFAULT \'False\','
             'NfoExport VARCHAR(5) NOT NULL DEFAULT \'False\','
             'PRIMARY KEY (TvShowID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    alter_tbl = ('ALTER TABLE netflix_addon.video_lib_tvshows '
                 'ADD UNIQUE INDEX UK_videolibtvshows_TvShowID(TvShowID);')
    cur.execute(table)
    cur.execute(alter_tbl)

    table = ('CREATE TABLE netflix_addon.watched_status_override ('
             'ProfileGuid VARCHAR(50) NOT NULL,'
             'VideoID INT(11) NOT NULL,'
             'Value TEXT DEFAULT NULL,'
             'PRIMARY KEY (ProfileGuid, VideoID))'
             'ENGINE = INNODB, CHARACTER SET utf8mb4, COLLATE utf8mb4_unicode_ci;')
    alter_tbl = ('ALTER TABLE netflix_addon.watched_status_override '
                 'ADD CONSTRAINT FK_watchedstatusoverride_ProfileGuid FOREIGN KEY (ProfileGuid)'
                 'REFERENCES netflix_addon.profiles(Guid) ON DELETE CASCADE ON UPDATE CASCADE;')
    cur.execute(table)
    cur.execute(alter_tbl)

    if conn and conn.is_connected():
        conn.close()
