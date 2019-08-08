# -*- coding: utf-8 -*-
"""Local database access and functions"""
from __future__ import unicode_literals

import sqlite3 as sql

import resources.lib.common as common
import resources.lib.database.db_base as db_base
import resources.lib.database.db_local as db_local
import resources.lib.database.db_utils as db_utils


class NFSharedDatabase(db_local.NFLocalDatabase):
    def get_value(self, key, default_value=None, table=db_utils.TABLE_SHARED_APP_CONF,
                  data_type=None):
        return super(NFSharedDatabase, self).get_value(key, default_value, table, data_type)

    def get_values(self, key, default_value=None, table=db_utils.TABLE_SHARED_APP_CONF):
        return super(NFSharedDatabase, self).get_values(key, default_value, table)

    def set_value(self, key, value, table=db_utils.TABLE_SHARED_APP_CONF):
        super(NFSharedDatabase, self).set_value(key, value, table)

    def delete_key(self, key, table=db_utils.TABLE_SHARED_APP_CONF):
        super(NFSharedDatabase, self).delete_key(key, table)

    @db_base.sql_connect()
    def get_movie_filepath(self, movieid, default_value=None):
        """Get movie filepath for given id"""
        query = 'SELECT FilePath FROM VideoLibMovies WHERE MovieID = ?'
        cur = self._execute_query(query, (movieid,))
        result = cur.fetchone()
        return result[0] if result else default_value

    @db_base.sql_connect()
    def get_episode_filepath(self, tvshowid, seasonid, episodeid, default_value=None):
        """Get movie filepath for given id"""
        query =\
            ('SELECT FilePath FROM VideoLibEpisodes '
             'INNER JOIN VideoLibSeasons ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
             'WHERE VideoLibSeasons.TvShowID = ? AND '
             'VideoLibSeasons.SeasonID = ? AND '
             'VideoLibEpisodes.EpisodeID = ?')
        cur = self._execute_query(query, (tvshowid, seasonid, episodeid))
        result = cur.fetchone()
        return result[0] if result is not None else default_value

    @db_base.sql_connect()
    def get_all_episodes_ids_and_filepath_from_tvshow(self, tvshowid):
        """Get all episodes IDs and filepaths for given id"""
        self.conn.row_factory = sql.Row
        query =\
            ('SELECT VideoLibEpisodes.FilePath, VideoLibSeasons.TvShowID, '
             'VideoLibEpisodes.SeasonID, VideoLibEpisodes.EpisodeID '
             'FROM VideoLibEpisodes '
             'INNER JOIN VideoLibSeasons ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
             'WHERE VideoLibSeasons.TvShowID = ?')
        cur = self._execute_query(query, (tvshowid,))
        result = cur.fetchall()
        return result

    @db_base.sql_connect()
    def get_all_episodes_ids_and_filepath_from_season(self, tvshowid, seasonid):
        """Get all episodes IDs and filepaths for given id"""
        self.conn.row_factory = sql.Row
        query =\
            ('SELECT VideoLibEpisodes.FilePath, VideoLibSeasons.TvShowID, '
             'VideoLibEpisodes.SeasonID, VideoLibEpisodes.EpisodeID '
             'FROM VideoLibEpisodes '
             'INNER JOIN VideoLibSeasons ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
             'WHERE VideoLibSeasons.TvShowID = ? AND '
             'VideoLibSeasons.SeasonID = ?')
        cur = self._execute_query(query, (tvshowid, seasonid))
        result = cur.fetchall()
        return result

    @db_base.sql_connect()
    def get_random_episode_filepath_from_tvshow(self, tvshowid, default_value=None):
        """Get random episode filepath of a show of a given id"""
        query =\
            ('SELECT FilePath FROM VideoLibEpisodes '
             'INNER JOIN VideoLibSeasons ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
             'WHERE VideoLibSeasons.TvShowID = ? '
             'ORDER BY RANDOM() LIMIT 1')
        cur = self._execute_query(query, (tvshowid,))
        result = cur.fetchone()
        return result[0] if result is not None else default_value

    @db_base.sql_connect()
    def get_random_episode_filepath_from_season(self, tvshowid, seasonid, default_value=None):
        """Get random episode filepath of a show of a given id"""
        query =\
            ('SELECT FilePath FROM VideoLibEpisodes '
             'INNER JOIN VideoLibSeasons ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
             'WHERE VideoLibSeasons.TvShowID = ? AND VideoLibSeasons.SeasonID = ? '
             'ORDER BY RANDOM() LIMIT 1')
        cur = self._execute_query(query, (tvshowid, seasonid))
        result = cur.fetchone()
        return result[0] if result is not None else default_value

    @db_base.sql_connect()
    def get_all_video_id_list(self):
        """Get all the ids of movies and tvshows contained in the library"""
        self.conn.row_factory = lambda cursor, row: row[0]
        query = ('SELECT MovieID FROM VideoLibMovies '
                 'UNION '
                 'SELECT TvShowID FROM VideoLibTvShows')
        cur = self._execute_query(query)
        result = cur.fetchall()
        return result

    @db_base.sql_connect()
    def get_tvshows_id_list(self, enum_vid_prop=None, prop_value=None):
        """
        Get all the ids of tvshows contained in the library
        :param enum_vid_prop: Optional: use db_utils.VidLibProp
        :param prop_value: Optional: value as filter
        :return: list of tvshows ids
        """
        self.conn.row_factory = lambda cursor, row: row[0]
        if enum_vid_prop and prop_value:
            query = ('SELECT TvShowID FROM VideoLibTvShows'
                     'WHERE ' + enum_vid_prop.value + ' = ?')
            cur = self._execute_query(query, (str(prop_value),))
        else:
            query = 'SELECT TvShowID FROM VideoLibTvShows'
            cur = self._execute_query(query)
        result = cur.fetchall()
        return result

    @db_base.sql_connect()
    def get_movies_id_list(self):
        """Get all the ids of movies contained in the library"""
        self.conn.row_factory = lambda cursor, row: row[0]
        query = 'SELECT MovieID FROM VideoLibMovies'
        cur = self._execute_query(query)
        result = cur.fetchall()
        return result

    @db_base.sql_connect()
    def movie_id_exists(self, movieid):
        """Return True if a movie id exists"""
        query = 'SELECT EXISTS(SELECT 1 FROM VideoLibMovies WHERE MovieID = ?)'
        cur = self._execute_query(query, (movieid,))
        return bool(cur.fetchone()[0])

    @db_base.sql_connect()
    def tvshow_id_exists(self, tvshowid):
        """Return True if a tvshow id exists"""
        query = 'SELECT EXISTS(SELECT 1 FROM VideoLibTvShows WHERE TvShowID = ?)'
        cur = self._execute_query(query, (tvshowid,))
        return bool(cur.fetchone()[0])

    @db_base.sql_connect()
    def season_id_exists(self, tvshowid, seasonid):
        """Return True if a tvshow season id exists"""
        query =\
            ('SELECT EXISTS('
             'SELECT 1 FROM VideoLibSeasons '
             'INNER JOIN VideoLibTvShows ON VideoLibSeasons.TvShowID = VideoLibTvShows.TvShowID '
             'WHERE VideoLibTvShows.TvShowID = ? AND VideoLibSeasons.SeasonID = ?)')
        cur = self._execute_query(query, (tvshowid, seasonid))
        return bool(cur.fetchone()[0])

    @db_base.sql_connect()
    def episode_id_exists(self, tvshowid, seasonid, episodeid):
        """Return True if a tvshow episode id exists"""
        query =\
            ('SELECT EXISTS('
             'SELECT 1 FROM VideoLibEpisodes '
             'INNER JOIN VideoLibSeasons ON VideoLibEpisodes.SeasonID = VideoLibSeasons.SeasonID '
             'INNER JOIN VideoLibTvShows ON VideoLibSeasons.TvShowID = VideoLibTvShows.TvShowID '
             'WHERE VideoLibTvShows.TvShowID = ? AND '
             'VideoLibSeasons.SeasonID = ? AND '
             'VideoLibEpisodes.EpisodeID = ?)')
        cur = self._execute_query(query, (tvshowid, seasonid, episodeid))
        return bool(cur.fetchone()[0])

    @db_base.sql_connect()
    def set_movie(self, movieid, file_path, nfo_export):
        """Update or insert a movie"""
        # Update or insert approach, if there is no updated row then insert new one
        update_query = ('UPDATE VideoLibMovies SET FilePath = ?, NfoExport = ? '
                        'WHERE MovieID = ?')
        cur = self._execute_query(update_query, (file_path, nfo_export, movieid))
        if cur.rowcount == 0:
            insert_query =\
                'INSERT INTO VideoLibMovies (MovieID, FilePath, NfoExport) VALUES (?, ?, ?)'
            self._execute_non_query(insert_query, (movieid, file_path, nfo_export))

    @db_base.sql_connect()
    def set_tvshow(self, tvshowid, nfo_export, exclude_update):
        """Update or insert a tvshow"""
        # Update or insert approach, if there is no updated row then insert new one
        update_query = ('UPDATE VideoLibTvShows SET NfoExport = ?, ExcludeUpdate = ? '
                        'WHERE TvShowID = ?')
        cur = self._execute_query(update_query, (str(nfo_export), str(exclude_update), tvshowid))
        if cur.rowcount == 0:
            insert_query =\
                ('INSERT INTO VideoLibTvShows (TvShowID, NfoExport, ExcludeUpdate) '
                 'VALUES (?, ?, ?)')
            self._execute_non_query(insert_query, (tvshowid, str(nfo_export), str(exclude_update)))

    @db_base.sql_connect()
    def insert_season(self, tvshowid, seasonid):
        """Insert a season if not exists"""
        if not self.season_id_exists(tvshowid, seasonid):
            insert_query = ('INSERT INTO VideoLibSeasons (TvShowID, SeasonID) '
                            'VALUES (?, ?)')
            self._execute_non_query(insert_query, (tvshowid, seasonid))

    @db_base.sql_connect()
    def insert_episode(self, tvshowid, seasonid, episodeid, file_path):
        """Insert a episode if not exists"""
        if not self.episode_id_exists(tvshowid, seasonid, episodeid):
            insert_query = ('INSERT INTO VideoLibEpisodes (SeasonID, EpisodeID, FilePath) '
                            'VALUES (?, ?, ?)')
            self._execute_non_query(insert_query, (seasonid, episodeid, file_path))

    @db_base.sql_connect()
    def delete_movie(self, movieid):
        """Delete a movie from database"""
        query = 'DELETE FROM VideoLibMovies WHERE MovieID = ?'
        self._execute_query(query, (movieid,))

    @db_base.sql_connect()
    def delete_tvshow(self, tvshowid):
        """Delete a tvshow from database"""
        query = 'DELETE FROM VideoLibTvShows WHERE TvShowID = ?'
        self._execute_query(query, (tvshowid,))

    @db_base.sql_connect()
    def delete_season(self, tvshowid, seasonid):
        """Delete a season from database"""
        query = 'DELETE FROM VideoLibSeasons WHERE TvShowID = ? AND SeasonID = ?'
        self._execute_query(query, (tvshowid, seasonid))
        # if there are no other seasons, delete the tvshow
        query = 'SELECT EXISTS(SELECT 1 FROM VideoLibSeasons WHERE TvShowID = ?)'
        cur = self._execute_query(query, (tvshowid,))
        if not bool(cur.fetchone()[0]):
            self.delete_tvshow(tvshowid)

    @db_base.sql_connect()
    def delete_episode(self, tvshowid, seasonid, episodeid):
        """Delete a episode from database"""
        query = 'DELETE FROM VideoLibEpisodes WHERE SeasonID = ? AND EpisodeID = ?'
        self._execute_query(query, (seasonid, episodeid))
        # if there are no other episodes, delete the season
        query = 'SELECT EXISTS(SELECT 1 FROM VideoLibEpisodes WHERE SeasonID = ?)'
        cur = self._execute_query(query, (seasonid,))
        if not bool(cur.fetchone()[0]):
            self.delete_season(tvshowid, seasonid)

    @db_base.sql_connect()
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

    @db_base.sql_connect()
    def set_tvshow_property(self, tvshowid, enum_vid_prop, value):
        update_query = ('UPDATE VideoLibTvShows '
                        'SET ' + enum_vid_prop.value + ' = ? WHERE TvShowID = ?')
        value = common.convert_to_string(value)
        cur = self._execute_query(update_query, (value, tvshowid))

    @db_base.sql_connect()
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

    @db_base.sql_connect()
    def set_stream_continuity(self, profile_guid, videoid, value):
        """Update or insert a stream continuity value to current profile"""
        # Update or insert approach, if there is no updated row then insert new one
        value = common.convert_to_string(value)
        update_query = ('UPDATE StreamContinuity '
                        'SET Value = ?, DateLastModified = datetime(\'now\', \'localtime\') '
                        'WHERE ProfileGuid = ? AND VideoID = ?')
        cur = self._execute_query(update_query, (value, profile_guid, videoid))
        if cur.rowcount == 0:
            insert_query = ('INSERT INTO StreamContinuity '
                            '(ProfileGuid, VideoID, Value, DateLastModified) '
                            'VALUES (?, ?, ?, datetime(\'now\', \'localtime\'))')
            self._execute_non_query(insert_query, (profile_guid, videoid, value))
