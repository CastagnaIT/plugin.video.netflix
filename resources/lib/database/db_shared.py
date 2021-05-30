# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT (original implementation module)
    Sharable database access and functions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from datetime import datetime

import resources.lib.common as common
import resources.lib.database.db_base_mysql as db_base_mysql
import resources.lib.database.db_base_sqlite as db_base_sqlite
import resources.lib.database.db_utils as db_utils
from resources.lib.common.exceptions import DBRecordNotExistError


def get_shareddb_class(use_mysql=False):
    # Dynamically sets the inherit class
    base_class = db_base_mysql.MySQLDatabase if use_mysql else db_base_sqlite.SQLiteDatabase

    class NFSharedDatabase(base_class):
        def __init__(self):
            if use_mysql:
                super().__init__(None)
            else:
                super().__init__(db_utils.SHARED_DB_FILENAME)

        def get_value(self, key, default_value=None, table=db_utils.TABLE_SHARED_APP_CONF, data_type=None):  # pylint: disable=useless-super-delegation
            return super().get_value(key, default_value, table, data_type)

        def get_values(self, key, default_value=None, table=db_utils.TABLE_SHARED_APP_CONF):  # pylint: disable=useless-super-delegation
            return super().get_values(key, default_value, table)

        def set_value(self, key, value, table=db_utils.TABLE_SHARED_APP_CONF):  # pylint: disable=useless-super-delegation
            super().set_value(key, value, table)

        def delete_key(self, key, table=db_utils.TABLE_SHARED_APP_CONF):  # pylint: disable=useless-super-delegation
            super().delete_key(key, table)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_profile(self, guid, sort_order):
            """Update or Insert a profile"""
            # Update or insert approach,
            # if there is no updated row then insert new one (no id changes)
            if self.is_mysql_database:
                query = db_utils.mysql_insert_or_update('profiles', ['Guid'], ['SortOrder'])
                self._execute_non_query(query, (guid, sort_order), multi=True)
            else:
                data = db_utils.sql_filtered_update('profiles',
                                                    ['SortOrder'],
                                                    ['Guid'],
                                                    [sort_order, guid])
                cur = self._execute_query(data[0], data[1])
                if cur.rowcount == 0:
                    data = db_utils.sql_filtered_insert('profiles',
                                                        ['Guid', 'SortOrder'],
                                                        [guid, sort_order])
                    self._execute_non_query(data[0], data[1])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_profile(self, guid):
            query = 'DELETE FROM profiles WHERE Guid = ?'
            self._execute_non_query(query, (guid,))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_movie_filepath(self, movieid):
            """Get movie filepath for given id"""
            query = 'SELECT FilePath FROM video_lib_movies WHERE MovieID = ?'
            cur = self._execute_query(query, (movieid,))
            result = cur.fetchone()
            if not result:
                raise DBRecordNotExistError
            return result[0]

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_episode_filepath(self, tvshowid, seasonid, episodeid):
            """Get movie filepath for given id"""
            query =\
                ('SELECT FilePath FROM video_lib_episodes '
                 'INNER JOIN video_lib_seasons '
                 'ON video_lib_episodes.SeasonID = video_lib_seasons.SeasonID '
                 'WHERE video_lib_seasons.TvShowID = ? AND '
                 'video_lib_seasons.SeasonID = ? AND '
                 'video_lib_episodes.EpisodeID = ?')
            cur = self._execute_query(query, (tvshowid, seasonid, episodeid))
            result = cur.fetchone()
            if not result:
                raise DBRecordNotExistError
            return result[0]

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_all_episodes_ids_and_filepath_from_tvshow(self, tvshowid):
            """Get all episodes IDs and filepaths for given id"""
            cur = self.get_cursor_for_dict_results()
            query =\
                ('SELECT video_lib_episodes.FilePath, video_lib_seasons.TvShowID, '
                 'video_lib_episodes.SeasonID, video_lib_episodes.EpisodeID '
                 'FROM video_lib_episodes '
                 'INNER JOIN video_lib_seasons '
                 'ON video_lib_episodes.SeasonID = video_lib_seasons.SeasonID '
                 'WHERE video_lib_seasons.TvShowID = ?')
            cur = self._execute_query(query, (tvshowid,), cur)
            result = cur.fetchall()
            if not result:
                raise DBRecordNotExistError
            return result

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_all_episodes_ids_and_filepath_from_season(self, tvshowid, seasonid):
            """Get all episodes IDs and filepaths for given id"""
            cur = self.get_cursor_for_dict_results()
            query =\
                ('SELECT video_lib_episodes.FilePath, video_lib_seasons.TvShowID, '
                 'video_lib_episodes.SeasonID, video_lib_episodes.EpisodeID '
                 'FROM video_lib_episodes '
                 'INNER JOIN video_lib_seasons '
                 'ON video_lib_episodes.SeasonID = video_lib_seasons.SeasonID '
                 'WHERE video_lib_seasons.TvShowID = ? AND '
                 'video_lib_seasons.SeasonID = ?')
            cur = self._execute_query(query, (tvshowid, seasonid), cur)
            result = cur.fetchall()
            if not result:
                raise DBRecordNotExistError
            return result

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_random_episode_filepath_from_tvshow(self, tvshowid):
            """Get random episode filepath of a show of a given id"""
            rand_func_name = 'RAND()' if self.is_mysql_database else 'RANDOM()'
            query =\
                ('SELECT FilePath FROM video_lib_episodes '
                 'INNER JOIN video_lib_seasons '
                 'ON video_lib_episodes.SeasonID = video_lib_seasons.SeasonID '
                 'WHERE video_lib_seasons.TvShowID = ? '
                 f'ORDER BY {rand_func_name} LIMIT 1')
            cur = self._execute_query(query, (tvshowid,))
            result = cur.fetchone()
            if not result:
                raise DBRecordNotExistError
            return result[0]

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_random_episode_filepath_from_season(self, tvshowid, seasonid):
            """Get random episode filepath of a show of a given id"""
            rand_func_name = 'RAND()' if self.is_mysql_database else 'RANDOM()'
            query =\
                ('SELECT FilePath FROM video_lib_episodes '
                 'INNER JOIN video_lib_seasons '
                 'ON video_lib_episodes.SeasonID = video_lib_seasons.SeasonID '
                 'WHERE video_lib_seasons.TvShowID = ? AND video_lib_seasons.SeasonID = ? '
                 f'ORDER BY {rand_func_name} LIMIT 1')
            cur = self._execute_query(query, (tvshowid, seasonid))
            result = cur.fetchone()
            if not result:
                raise DBRecordNotExistError
            return result[0]

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_all_video_id_list(self):
            """Get all the ids of movies and tvshows contained in the library"""
            cur = self.get_cursor_for_list_results()
            query = ('SELECT MovieID FROM video_lib_movies '
                     'UNION '
                     'SELECT TvShowID FROM video_lib_tvshows')
            cur = self._execute_query(query, cursor=cur)
            return self.return_rows_as_list(cur)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_tvshows_id_list(self, enum_vid_prop=None, prop_value=None):
            """
            Get all the ids of tvshows contained in the library
            :param enum_vid_prop: Optional: use db_utils.VidLibProp
            :param prop_value: Optional: value as filter
            :return: list of tvshows ids
            """
            cur = self.get_cursor_for_list_results()
            if enum_vid_prop and prop_value:
                query = ('SELECT TvShowID FROM video_lib_tvshows '
                         f'WHERE {enum_vid_prop} = ?')
                cur = self._execute_query(query, (str(prop_value),), cur)
            else:
                query = 'SELECT TvShowID FROM video_lib_tvshows'
                cur = self._execute_query(query, cursor=cur)
            return self.return_rows_as_list(cur)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_movies_id_list(self):
            """Get all the ids of movies contained in the library"""
            cur = self.get_cursor_for_list_results()
            query = 'SELECT MovieID FROM video_lib_movies'
            cur = self._execute_query(query, cursor=cur)
            return self.return_rows_as_list(cur)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def movie_id_exists(self, movieid):
            """Return True if a movie id exists"""
            query = 'SELECT EXISTS(SELECT 1 FROM video_lib_movies WHERE MovieID = ?)'
            cur = self._execute_query(query, (movieid,))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def tvshow_id_exists(self, tvshowid):
            """Return True if a tvshow id exists"""
            query = 'SELECT EXISTS(SELECT 1 FROM video_lib_tvshows WHERE TvShowID = ?)'
            cur = self._execute_query(query, (tvshowid,))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def season_id_exists(self, tvshowid, seasonid):
            """Return True if a tvshow season id exists"""
            query =\
                ('SELECT EXISTS('
                 'SELECT 1 FROM video_lib_seasons '
                 'INNER JOIN video_lib_tvshows '
                 'ON video_lib_seasons.TvShowID = video_lib_tvshows.TvShowID '
                 'WHERE video_lib_tvshows.TvShowID = ? AND video_lib_seasons.SeasonID = ?)')
            cur = self._execute_query(query, (tvshowid, seasonid))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def episode_id_exists(self, tvshowid, seasonid, episodeid):
            """Return True if a tvshow episode id exists"""
            query =\
                ('SELECT EXISTS('
                 'SELECT 1 FROM video_lib_episodes '
                 'INNER JOIN video_lib_seasons '
                 'ON video_lib_episodes.SeasonID = video_lib_seasons.SeasonID '
                 'INNER JOIN video_lib_tvshows '
                 'ON video_lib_seasons.TvShowID = video_lib_tvshows.TvShowID '
                 'WHERE video_lib_tvshows.TvShowID = ? AND '
                 'video_lib_seasons.SeasonID = ? AND '
                 'video_lib_episodes.EpisodeID = ?)')
            cur = self._execute_query(query, (tvshowid, seasonid, episodeid))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_movie(self, movieid, file_path, nfo_export):
            """Update or insert a movie"""
            # Update or insert approach, if there is no updated row then insert new one
            if self.is_mysql_database:
                query = db_utils.mysql_insert_or_update('video_lib_movies', ['MovieID'],
                                                        ['FilePath', 'NfoExport'])
                self._execute_non_query(query, (movieid, file_path, str(nfo_export)), multi=True)
            else:
                update_query = ('UPDATE video_lib_movies SET FilePath = ?, NfoExport = ? '
                                'WHERE MovieID = ?')
                cur = self._execute_query(update_query, (file_path, str(nfo_export), movieid))
                if cur.rowcount == 0:
                    insert_query = ('INSERT INTO video_lib_movies (MovieID, FilePath, NfoExport) '
                                    'VALUES (?, ?, ?)')
                    self._execute_non_query(insert_query, (movieid, file_path, str(nfo_export)))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_tvshow(self, tvshowid, nfo_export, exclude_update):
            """Update or insert a tvshow"""
            # Update or insert approach, if there is no updated row then insert new one
            if self.is_mysql_database:
                query = db_utils.mysql_insert_or_update('video_lib_tvshows', ['TvShowID'],
                                                        ['ExcludeUpdate', 'NfoExport'])
                self._execute_non_query(query, (tvshowid, str(exclude_update), str(nfo_export)),
                                        multi=True)
            else:
                update_query = ('UPDATE video_lib_tvshows SET NfoExport = ?, ExcludeUpdate = ? '
                                'WHERE TvShowID = ?')
                cur = self._execute_query(update_query, (str(nfo_export),
                                                         str(exclude_update), tvshowid))
                if cur.rowcount == 0:
                    insert_query = \
                        ('INSERT INTO video_lib_tvshows (TvShowID, NfoExport, ExcludeUpdate) '
                         'VALUES (?, ?, ?)')
                    self._execute_non_query(insert_query, (tvshowid,
                                                           str(nfo_export),
                                                           str(exclude_update)))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def insert_season(self, tvshowid, seasonid):
            """Insert a season if not exists"""
            if not self.season_id_exists(tvshowid, seasonid):
                insert_query = ('INSERT INTO video_lib_seasons (TvShowID, SeasonID) '
                                'VALUES (?, ?)')
                self._execute_non_query(insert_query, (tvshowid, seasonid))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def insert_episode(self, tvshowid, seasonid, episodeid, file_path):
            """Insert a episode if not exists"""
            if not self.episode_id_exists(tvshowid, seasonid, episodeid):
                insert_query = ('INSERT INTO video_lib_episodes (SeasonID, EpisodeID, FilePath) '
                                'VALUES (?, ?, ?)')
                self._execute_non_query(insert_query, (seasonid, episodeid, file_path))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_movie(self, movieid):
            """Delete a movie from database"""
            query = 'DELETE FROM video_lib_movies WHERE MovieID = ?'
            self._execute_query(query, (movieid,))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_tvshow(self, tvshowid):
            """Delete a tvshow from database"""
            query = 'DELETE FROM video_lib_tvshows WHERE TvShowID = ?'
            self._execute_query(query, (tvshowid,))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_season(self, tvshowid, seasonid):
            """Delete a season from database"""
            query = 'DELETE FROM video_lib_seasons WHERE TvShowID = ? AND SeasonID = ?'
            self._execute_query(query, (tvshowid, seasonid))
            # if there are no other seasons, delete the tvshow
            query = 'SELECT EXISTS(SELECT 1 FROM video_lib_seasons WHERE TvShowID = ?)'
            cur = self._execute_query(query, (tvshowid,))
            if not bool(cur.fetchone()[0]):
                self.delete_tvshow(tvshowid)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_episode(self, tvshowid, seasonid, episodeid):
            """Delete a episode from database"""
            query = 'DELETE FROM video_lib_episodes WHERE SeasonID = ? AND EpisodeID = ?'
            self._execute_query(query, (seasonid, episodeid))
            # if there are no other episodes, delete the season
            query = 'SELECT EXISTS(SELECT 1 FROM video_lib_episodes WHERE SeasonID = ?)'
            cur = self._execute_query(query, (seasonid,))
            if not bool(cur.fetchone()[0]):
                self.delete_season(tvshowid, seasonid)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_tvshow_property(self, tvshowid, enum_vid_prop, default_value=None, data_type=None):
            """
            Read the value of the specified property
            :param tvshowid: id of tvshow
            :param enum_vid_prop: Use a enum value of db_utils.VidLibProp
            :param default_value: When key do not exist return this default value
            :param data_type: OPTIONAL Used to set data type conversion only when default_value is None
            :return: the property value
            """
            query = f'SELECT {enum_vid_prop} FROM video_lib_tvshows WHERE TvShowID = ?'
            cur = self._execute_query(query, (tvshowid,))
            result = cur.fetchone()
            if default_value is not None:
                data_type = type(default_value)
            elif data_type is None:
                data_type = str
            return common.convert_from_string(result[0], data_type) \
                if result is not None else default_value

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_tvshow_property(self, tvshowid, enum_vid_prop, value):
            update_query = ('UPDATE video_lib_tvshows '
                            f'SET {enum_vid_prop} = ? WHERE TvShowID = ?')
            value = common.convert_to_string(value)
            self._execute_query(update_query, (value, tvshowid))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_watched_status(self, profile_guid, videoid, default_value=None, data_type=None):
            """Get override watched status value of a given id stored to current profile"""
            query = 'SELECT Value FROM watched_status_override WHERE ProfileGuid = ? AND VideoID = ?'
            cur = self._execute_query(query, (profile_guid, videoid))
            result = cur.fetchone()
            if default_value is not None:
                data_type = type(default_value)
            elif data_type is None:
                data_type = str
            return common.convert_from_string(result[0], data_type) \
                if result is not None else default_value

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_watched_status(self, profile_guid, videoid, value):
            """Update or insert the watched status override value to current profile"""
            # Update or insert approach, if there is no updated row then insert new one
            value = common.convert_to_string(value)
            if self.is_mysql_database:
                query = db_utils.mysql_insert_or_update('watched_status_override',
                                                        ['ProfileGuid', 'VideoID'],
                                                        ['Value'])
                self._execute_non_query(query, (profile_guid, videoid, value),
                                        multi=True)
            else:
                update_query = ('UPDATE watched_status_override '
                                'SET Value = ? '
                                'WHERE ProfileGuid = ? AND VideoID = ?')
                cur = self._execute_query(update_query, (value, profile_guid, videoid))
                if cur.rowcount == 0:
                    insert_query = ('INSERT INTO watched_status_override '
                                    '(ProfileGuid, VideoID, Value) '
                                    'VALUES (?, ?, ?)')
                    self._execute_non_query(insert_query, (profile_guid, videoid, value))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_watched_status(self, profile_guid, videoid):
            """Delete a watched status override from database"""
            query = 'DELETE FROM watched_status_override WHERE ProfileGuid = ? AND VideoID = ?'
            self._execute_query(query, (profile_guid, videoid))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_stream_continuity(self, profile_guid, videoid, default_value=None, data_type=None):
            """Get stream continuity value of a given id stored to current profile"""
            query = 'SELECT Value FROM stream_continuity WHERE ProfileGuid = ? AND VideoID = ?'
            cur = self._execute_query(query, (profile_guid, videoid))
            result = cur.fetchone()
            if default_value is not None:
                data_type = type(default_value)
            elif data_type is None:
                data_type = str
            return common.convert_from_string(result[0], data_type) \
                if result is not None else default_value

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_stream_continuity(self, profile_guid, videoid, value):
            """Update or insert a stream continuity value to current profile"""
            # Update or insert approach, if there is no updated row then insert new one
            value = common.convert_to_string(value)
            date_last_modified = common.convert_to_string(datetime.now())
            if self.is_mysql_database:
                query = db_utils.mysql_insert_or_update('stream_continuity',
                                                        ['ProfileGuid', 'VideoID'],
                                                        ['Value', 'DateLastModified'])
                self._execute_non_query(query, (profile_guid, videoid, value, date_last_modified),
                                        multi=True)
            else:
                update_query = ('UPDATE stream_continuity '
                                'SET Value = ?, DateLastModified = ? '
                                'WHERE ProfileGuid = ? AND VideoID = ?')
                cur = self._execute_query(update_query, (value, date_last_modified,
                                                         profile_guid, videoid))
                if cur.rowcount == 0:
                    insert_query = ('INSERT INTO stream_continuity '
                                    '(ProfileGuid, VideoID, Value, DateLastModified) '
                                    'VALUES (?, ?, ?, ?)')
                    self._execute_non_query(insert_query, (profile_guid, videoid,
                                                           value, date_last_modified))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def clear_stream_continuity(self):
            """Clear all stream continuity data"""
            query = 'DELETE FROM stream_continuity'
            self._execute_non_query(query)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def purge_library(self):
            """Delete all records from library tables"""
            query = 'DELETE FROM video_lib_movies'
            self._execute_non_query(query)
            query = 'DELETE FROM video_lib_episodes'
            self._execute_non_query(query)
            query = 'DELETE FROM video_lib_seasons'
            self._execute_non_query(query)
            query = 'DELETE FROM video_lib_tvshows'
            self._execute_non_query(query)

    return NFSharedDatabase
