#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: LibraryExporter
# Created on: 13.01.2017

import os
import pickle
from utils import noop

class Library:
    """Exports Netflix shows & movies to a local library folder (Not yet ready)"""

    series_label = 'shows'
    movies_label = 'movies'
    db_filename = 'lib.ndb'


    def __init__ (self, base_url, root_folder, library_settings, log_fn=noop):
        """Takes the instances & configuration options needed to drive the plugin

        Parameters
        ----------
        base_url : :obj:`str`
            Plugin base url

        root_folder : :obj:`str`
            Cookie location

        library_settings : :obj:`str`
            User data cache location

        library_db_path : :obj:`str`
            User data cache location

        log_fn : :obj:`fn`
             optional log function
        """
        self.base_url = base_url
        self.base_data_path = root_folder
        self.enable_custom_library_folder = library_settings['enablelibraryfolder']
        self.custom_library_folder = library_settings['customlibraryfolder']
        self.log = log_fn
        self.db_filepath = os.path.join(self.base_data_path, self.db_filename)

        # check for local library folder & set up the paths
        if self.enable_custom_library_folder != 'true':
            self.movie_path = os.path.join(self.base_data_path, self.series_label)
            self.tvshow_path = os.path.join(self.base_data_path, self.movies_label)
        else:
            self.movie_path = os.path.join(self.custom_library_folder, self.movies_label)
            self.tvshow_path = os.path.join(self.custom_library_folder, self.series_label)

        self.setup_local_netflix_library(source={
            self.movies_label: self.movie_path,
            self.series_label: self.tvshow_path
        })

        self.db = self._load_local_db(filename=self.db_filepath)

    def setup_local_netflix_library (self, source):
        for label in source:
            if not os.path.exists(source[label]):
                os.makedirs(source[label])

    def write_strm_file(self, path, url):
        with open(path, 'w+') as f:
            f.write(url)
            f.close()

    def _load_local_db (self, filename):
        # if the db doesn't exist, create it
        if not os.path.isfile(filename):
            data = {self.movies_label: {}, self.series_label: {}}
            self.log('Setup local library DB')
            self._update_local_db(filename=filename, data=data)
            return data

        with open(filename) as f:
            data = pickle.load(f)
            if data:
                return data
            else:
                return {}

    def _update_local_db (self, filename, data):
        if not os.path.isdir(os.path.dirname(filename)):
            return False
        with open(filename, 'w') as f:
            f.truncate()
            pickle.dump(data, f)
        return True

    def movie_exists (self, title, year):
        movie_meta = '%s (%d)' % (title, year)
        return movie_meta in self.db[self.movies_label]

    def show_exists (self, title, year):
        show_meta = '%s (%d)' % (title, year)
        return show_meta in self.db[self.series_label]

    def season_exists (self, title, year, season):
        if self.show_exists() == False:
            return False
        show_meta = '%s (%d)' % (title, year)
        show_entry = self.db[self.series_label][show_meta]
        return season in show_entry['seasons']

    def episode_exists (self, title, year, season, episode):
        if self.show_exists() == False:
            return False
        show_meta = '%s (%d)' % (title, year)
        show_entry = self.db[self.series_label][show_meta]
        episode_entry = 'S%02dE%02d' % (season, episode)
        return episode_entry in show_entry['episodes']

    def add_movie(self, title, year, video_id, pin, build_url):
        movie_meta = '%s (%d)' % (title, year)
        dirname = os.path.join(self.movie_path, movie_meta)
        filename = os.path.join(dirname, movie_meta + '.strm')
        if os.path.exists(filename):
            return
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        if self.movie_exists(title=title, year=year) == False:
            self.db[self.movies_label][movie_meta] = True
            self._update_local_db(filename=self.db_filepath, db=self.db)
        self.write_strm_file(path=filename, url=build_url({'action': 'play_video', 'video_id': video_id, 'pin': pin}))

    def add_show(self, title, year, episodes, build_url):
        show_meta = '%s (%d)' % (title, year)
        show_dir = os.path.join(self.tvshow_path, show_meta)
        if not os.path.exists(show_dir):
            os.makedirs(show_dir)
        if self.show_exists(title, year) == False:
            self.db[self.series_label][show_meta] = {'seasons': [], 'episodes': []}
        for episode_id in episodes:
            episode = episodes[episode_id]
            self._add_episode(show_dir=show_dir, show_meta=show_meta, title=title, year=year, season=episode['season'], episode=episode['idx'], video_id=episode['id'], pin=episode['pin'], build_url=build_url)
        self._update_local_db(filename=self.db_filepath, db=self.db)
        return show_dir

    def _add_episode(self, title, year, show_dir, show_meta, season, episode, video_id, pin, build_url):
        season = int(season)
        episode = int(episode)

        # add season
        if self.season_exists(title=title, year=year, season=season) == False:
            self.db[self.series_label][show_meta]['seasons'].append(season)

        # add episode
        episode_meta = 'S%02dE%02d' % (season, episode)
        if self.episode_exists(title=title, year=year, season=season, episode=episode) == False:
            self.db[self.series_label][show_meta]['episodes'].append(episode_meta)

        # create strm file
        filename = episode_meta + '.strm'
        filepath = os.path.join(show_dir, filename)
        if os.path.exists(filepath):
            return
        self.write_strm_file(path=filepath, url=build_url({'action': 'play_video', 'video_id': video_id, 'pin': pin}))

    def remove_movie(self, title, year):
        movie_meta = '%s (%d)' % (title, year)
        del self.db[self.movies_label][movie_meta]
        self._update_local_db(filename=self.db_filepath, db=self.db)
        dirname = os.path.join(self.movie_path, movie_meta)
        if os.path.exists(dirname):
            os.rmtree(dirname)
            return True
        return False

    def remove_show(self, title, year):
        show_meta = '%s (%d)' % (title, year)
        del self.db[self.series_label][show_meta]
        self._update_local_db(filename=self.db_filepath, db=self.db)
        show_dir = os.path.join(self.tvshow_path, show_meta)
        if os.path.exists(show_dir):
            os.rmtree(show_dir)
            return True
        return False

    def remove_season(self, title, year, season):
        season = int(season)
        season_list = []
        episodes_list = []
        show_meta = '%s (%d)' % (title, year)
        for season_entry in self.db[self.series_label][show_meta]['seasons']:
            if season_entry != season:
                season_list.append(season_entry)
        self.db[self.series_label][show_meta]['seasons'] = season_list
        show_dir = os.path.join(self.tvshow_path, show_meta)
        if os.path.exists(show_dir):
            show_files = [f for f in os.listdir(show_dir) if os.path.isfile(os.path.join(show_dir, f))]
            for filename in show_files:
                if 'S%02dE' % (season) in filename:
                    os.remove(os.path.join(show_dir, filename))
                else:
                    episodes_list.append(filename.replace('.strm', ''))
            self.db[self.series_label][show_meta]['episodes'] = episodes_list
        self._update_local_db(filename=self.db_filepath, db=self.db)
        return True

    def remove_episode(self, title, year, season, episode):
        episodes_list = []
        show_meta = '%s (%d)' % (title, year)
        episode_meta = 'S%02dE%02d' % (season, episode)
        show_dir = os.path.join(self.tvshow_path, show_meta)
        if os.path.exists(os.path.join(show_dir, episode_meta + '.strm')):
            os.remove(os.path.join(show_dir, episode_meta + '.strm'))
        for episode_entry in self.db[self.series_label][show_meta]['episodes']:
            if episode_meta != episode_entry:
                episodes_list.append(episode_entry)
        self.db[self.series_label][show_meta]['episodes'] = episodes_list
        self._update_local_db(filename=self.db_filepath, db=self.db)
        return True
