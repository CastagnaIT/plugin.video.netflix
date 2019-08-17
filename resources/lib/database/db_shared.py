# -*- coding: utf-8 -*-
"""Shared database access and functions"""
from __future__ import unicode_literals

from datetime import datetime

import resources.lib.common as common
import resources.lib.database.db_base_mysql as db_base_mysql
import resources.lib.database.db_base_sqlite as db_base_sqlite
import resources.lib.database.db_utils as db_utils
from resources.lib.globals import g


def get_shareddb_class(force_sqlite=False):
    # Dynamically sets the inherit class
    use_mysql = g.ADDON.getSettingBool('use_mysql') and not force_sqlite
    base_class = db_base_mysql.MySQLDatabase if use_mysql else db_base_sqlite.SQLiteDatabase

    class NFSharedDatabase(base_class):
        def __init__(self):
            if use_mysql:
                super(NFSharedDatabase, self).__init__()
            else:
                super(NFSharedDatabase, self).__init__(db_utils.SHARED_DB_FILENAME)

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
                data = db_utils.sql_filtered_update('Profiles',
                                                    ['SortOrder'],
                                                    ['Guid'],
                                                    [sort_order, guid])
                cur = self._execute_query(data[0], data[1])
                if cur.rowcount == 0:
                    data = db_utils.sql_filtered_insert('Profiles',
                                                        ['Guid', 'SortOrder'],
                                                        [guid, sort_order])
                    self._execute_non_query(data[0], data[1])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_profile(self, guid):
            query = 'DELETE FROM Profiles WHERE Guid = ?'
            self._execute_non_query(query, (guid,))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_movie_filepath(self, movieid, default_value=None):
            """Get movie filepath for given id"""
            query = 'SELECT FilePath FROM VideoLibMovies WHERE MovieID = ?'
            cur = self._execute_query(query, (movieid,))
            result = cur.fetchone()
            return result[0] if result else default_value

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_episode_filepath(self, tvshowid, seasonid, episodeid, default_value=None):
            """Get movie filepath for given id"""
            query =\
                ('SELECT FilePath FROM VideoLibEpisodes '
                 'INNER JOIN VideoLibSeasons '
                 'ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
                 'WHERE VideoLibSeasons.TvShowID = ? AND '
                 'VideoLibSeasons.SeasonID = ? AND '
                 'VideoLibEpisodes.EpisodeID = ?')
            cur = self._execute_query(query, (tvshowid, seasonid, episodeid))
            result = cur.fetchone()
            return result[0] if result is not None else default_value

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_all_episodes_ids_and_filepath_from_tvshow(self, tvshowid):
            """Get all episodes IDs and filepaths for given id"""
            cur = self.get_cursor_for_dict_results()
            query =\
                ('SELECT VideoLibEpisodes.FilePath, VideoLibSeasons.TvShowID, '
                 'VideoLibEpisodes.SeasonID, VideoLibEpisodes.EpisodeID '
                 'FROM VideoLibEpisodes '
                 'INNER JOIN VideoLibSeasons '
                 'ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
                 'WHERE VideoLibSeasons.TvShowID = ?')
            cur = self._execute_query(query, (tvshowid,), cur)
            return cur.fetchall()

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_all_episodes_ids_and_filepath_from_season(self, tvshowid, seasonid):
            """Get all episodes IDs and filepaths for given id"""
            cur = self.get_cursor_for_dict_results()
            query =\
                ('SELECT VideoLibEpisodes.FilePath, VideoLibSeasons.TvShowID, '
                 'VideoLibEpisodes.SeasonID, VideoLibEpisodes.EpisodeID '
                 'FROM VideoLibEpisodes '
                 'INNER JOIN VideoLibSeasons '
                 'ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
                 'WHERE VideoLibSeasons.TvShowID = ? AND '
                 'VideoLibSeasons.SeasonID = ?')
            cur = self._execute_query(query, (tvshowid, seasonid), cur)
            return cur.fetchall()

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_random_episode_filepath_from_tvshow(self, tvshowid, default_value=None):
            """Get random episode filepath of a show of a given id"""
            rand_func_name = 'RAND()' if self.is_mysql_database else 'RANDOM()'
            query =\
                ('SELECT FilePath FROM VideoLibEpisodes '
                 'INNER JOIN VideoLibSeasons '
                 'ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
                 'WHERE VideoLibSeasons.TvShowID = ? '
                 'ORDER BY {} LIMIT 1').format(rand_func_name)
            cur = self._execute_query(query, (tvshowid,))
            result = cur.fetchone()
            return result[0] if result is not None else default_value

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_random_episode_filepath_from_season(self, tvshowid, seasonid, default_value=None):
            """Get random episode filepath of a show of a given id"""
            rand_func_name = 'RAND()' if self.is_mysql_database else 'RANDOM()'
            query =\
                ('SELECT FilePath FROM VideoLibEpisodes '
                 'INNER JOIN VideoLibSeasons '
                 'ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
                 'WHERE VideoLibSeasons.TvShowID = ? AND VideoLibSeasons.SeasonID = ? '
                 'ORDER BY {} LIMIT 1').format(rand_func_name)
            cur = self._execute_query(query, (tvshowid, seasonid))
            result = cur.fetchone()
            return result[0] if result is not None else default_value

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_all_video_id_list(self):
            """Get all the ids of movies and tvshows contained in the library"""
            cur = self.get_cursor_for_list_results()
            query = ('SELECT MovieID FROM VideoLibMovies '
                     'UNION '
                     'SELECT TvShowID FROM VideoLibTvShows')
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
                query = ('SELECT TvShowID FROM VideoLibTvShows'
                         'WHERE ' + enum_vid_prop.value + ' = ?')
                cur = self._execute_query(query, (str(prop_value),), cur)
            else:
                query = 'SELECT TvShowID FROM VideoLibTvShows'
                cur = self._execute_query(query, cursor=cur)
            return self.return_rows_as_list(cur)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_movies_id_list(self):
            """Get all the ids of movies contained in the library"""
            cur = self.get_cursor_for_list_results()
            query = 'SELECT MovieID FROM VideoLibMovies'
            cur = self._execute_query(query, cursor=cur)
            return self.return_rows_as_list(cur)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def movie_id_exists(self, movieid):
            """Return True if a movie id exists"""
            query = 'SELECT EXISTS(SELECT 1 FROM VideoLibMovies WHERE MovieID = ?)'
            cur = self._execute_query(query, (movieid,))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def tvshow_id_exists(self, tvshowid):
            """Return True if a tvshow id exists"""
            query = 'SELECT EXISTS(SELECT 1 FROM VideoLibTvShows WHERE TvShowID = ?)'
            cur = self._execute_query(query, (tvshowid,))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def season_id_exists(self, tvshowid, seasonid):
            """Return True if a tvshow season id exists"""
            query =\
                ('SELECT EXISTS('
                 'SELECT 1 FROM VideoLibSeasons '
                 'INNER JOIN VideoLibTvShows '
                 'ON VideoLibSeasons.TvShowID = VideoLibTvShows.TvShowID '
                 'WHERE VideoLibTvShows.TvShowID = ? AND VideoLibSeasons.SeasonID = ?)')
            cur = self._execute_query(query, (tvshowid, seasonid))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def episode_id_exists(self, tvshowid, seasonid, episodeid):
            """Return True if a tvshow episode id exists"""
            query =\
                ('SELECT EXISTS('
                 'SELECT 1 FROM VideoLibEpisodes '
                 'INNER JOIN VideoLibSeasons '
                 'ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
                 'INNER JOIN VideoLibTvShows '
                 'ON VideoLibSeasons.TvShowID = VideoLibTvShows.TvShowID '
                 'WHERE VideoLibTvShows.TvShowID = ? AND '
                 'VideoLibSeasons.SeasonID = ? AND '
                 'VideoLibEpisodes.EpisodeID = ?)')
            cur = self._execute_query(query, (tvshowid, seasonid, episodeid))
            return bool(cur.fetchone()[0])

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_movie(self, movieid, file_path, nfo_export):
            """Update or insert a movie"""
            # Update or insert approach, if there is no updated row then insert new one
            if self.is_mysql_database:
                query = db_utils.mysql_insert_or_update('VideoLibMovies', ['MovieID'],
                                                        ['FilePath', 'NfoExport'])
                self._execute_non_query(query, (movieid, file_path, str(nfo_export)), multi=True)
            else:
                update_query = ('UPDATE VideoLibMovies SET FilePath = ?, NfoExport = ? '
                                'WHERE MovieID = ?')
                cur = self._execute_query(update_query, (file_path, str(nfo_export), movieid))
                if cur.rowcount == 0:
                    insert_query =\
                        'INSERT INTO VideoLibMovies (MovieID, FilePath, NfoExport) VALUES (?, ?, ?)'
                    self._execute_non_query(insert_query, (movieid, file_path, str(nfo_export)))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def set_tvshow(self, tvshowid, nfo_export, exclude_update):
            """Update or insert a tvshow"""
            # Update or insert approach, if there is no updated row then insert new one
            if self.is_mysql_database:
                query = db_utils.mysql_insert_or_update('videolibtvshows', ['TvShowID'],
                                                        ['ExcludeUpdate', 'NfoExport'])
                self._execute_non_query(query, (tvshowid, str(exclude_update), str(nfo_export)),
                                        multi=True)
            else:
                update_query = ('UPDATE VideoLibTvShows SET NfoExport = ?, ExcludeUpdate = ? '
                                'WHERE TvShowID = ?')
                cur = self._execute_query(update_query, (str(nfo_export),
                                                         str(exclude_update), tvshowid))
                if cur.rowcount == 0:
                    insert_query =\
                        ('INSERT INTO VideoLibTvShows (TvShowID, NfoExport, ExcludeUpdate) '
                         'VALUES (?, ?, ?)')
                    self._execute_non_query(insert_query, (tvshowid,
                                                           str(nfo_export),
                                                           str(exclude_update)))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def insert_season(self, tvshowid, seasonid):
            """Insert a season if not exists"""
            if not self.season_id_exists(tvshowid, seasonid):
                insert_query = ('INSERT INTO VideoLibSeasons (TvShowID, SeasonID) '
                                'VALUES (?, ?)')
                self._execute_non_query(insert_query, (tvshowid, seasonid))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def insert_episode(self, tvshowid, seasonid, episodeid, file_path):
            """Insert a episode if not exists"""
            if not self.episode_id_exists(tvshowid, seasonid, episodeid):
                insert_query = ('INSERT INTO VideoLibEpisodes (SeasonID, EpisodeID, FilePath) '
                                'VALUES (?, ?, ?)')
                self._execute_non_query(insert_query, (seasonid, episodeid, file_path))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_movie(self, movieid):
            """Delete a movie from database"""
            query = 'DELETE FROM VideoLibMovies WHERE MovieID = ?'
            self._execute_query(query, (movieid,))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_tvshow(self, tvshowid):
            """Delete a tvshow from database"""
            query = 'DELETE FROM VideoLibTvShows WHERE TvShowID = ?'
            self._execute_query(query, (tvshowid,))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_season(self, tvshowid, seasonid):
            """Delete a season from database"""
            query = 'DELETE FROM VideoLibSeasons WHERE TvShowID = ? AND SeasonID = ?'
            self._execute_query(query, (tvshowid, seasonid))
            # if there are no other seasons, delete the tvshow
            query = 'SELECT EXISTS(SELECT 1 FROM VideoLibSeasons WHERE TvShowID = ?)'
            cur = self._execute_query(query, (tvshowid,))
            if not bool(cur.fetchone()[0]):
                self.delete_tvshow(tvshowid)

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def delete_episode(self, tvshowid, seasonid, episodeid):
            """Delete a episode from database"""
            query = 'DELETE FROM VideoLibEpisodes WHERE SeasonID = ? AND EpisodeID = ?'
            self._execute_query(query, (seasonid, episodeid))
            # if there are no other episodes, delete the season
            query = 'SELECT EXISTS(SELECT 1 FROM VideoLibEpisodes WHERE SeasonID = ?)'
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
            query = 'SELECT ' + enum_vid_prop.value + ' FROM VideoLibTvShows WHERE TvShowID = ?'
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
            update_query = ('UPDATE VideoLibTvShows '
                            'SET ' + enum_vid_prop.value + ' = ? WHERE TvShowID = ?')
            value = common.convert_to_string(value)
            cur = self._execute_query(update_query, (value, tvshowid))

        @db_base_mysql.handle_connection
        @db_base_sqlite.handle_connection
        def get_stream_continuity(self, profile_guid, videoid, default_value=None, data_type=None):
            """Get stream continuity value of a given id stored to current profile"""
            query = 'SELECT Value FROM StreamContinuity WHERE ProfileGuid = ? AND VideoID = ?'
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
                query = db_utils.mysql_insert_or_update('StreamContinuity',
                                                        ['ProfileGuid', 'VideoID'],
                                                        ['Value', 'DateLastModified'])
                self._execute_non_query(query, (profile_guid, videoid, value, date_last_modified),
                                        multi=True)
            else:
                update_query = ('UPDATE StreamContinuity '
                                'SET Value = ?, DateLastModified = ? '
                                'WHERE ProfileGuid = ? AND VideoID = ?')
                cur = self._execute_query(update_query, (value, date_last_modified,
                                                         profile_guid, videoid))
                if cur.rowcount == 0:
                    insert_query = ('INSERT INTO StreamContinuity '
                                    '(ProfileGuid, VideoID, Value, DateLastModified) '
                                    'VALUES (?, ?, ?, ?)')
                    self._execute_non_query(insert_query, (profile_guid, videoid,
                                                           value, date_last_modified))

    return NFSharedDatabase
