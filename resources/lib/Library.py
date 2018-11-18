# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: LibraryExporter
# Created on: 13.01.2017

import os
import re
import time
import threading
import xbmc
import xbmcgui
import xbmcvfs
import requests
from utils import noop
from KodiHelper import KodiHelper
try:
    import cPickle as pickle
except:
    import pickle


class Library(object):
    """Exports Netflix shows & movies to a local library folder"""

    series_label = 'shows'
    """str: Label to identify shows"""

    movies_label = 'movies'
    """str: Label to identify movies"""

    metadata_label = 'metadata'
    """str: Label to identify metadata"""

    imagecache_label = 'imagecache'
    """str: Label to identify imagecache"""

    db_filename = 'lib.ndb'
    """str: (File)Name of the store for the database dump that contains
    all shows/movies added to the library"""

    def __init__(self, nx_common):
        """
        Takes the instances & configuration options needed to drive the plugin

        Parameters
        ----------
        root_folder : :obj:`str`
            Cookie location

        library_settings : :obj:`str`
            User data cache location

        library_db_path : :obj:`str`
            User data cache location

        log_fn : :obj:`fn`
             optional log function
        """

        enable_custom_folder = nx_common.get_setting('enablelibraryfolder')
        self.nx_common = nx_common
        self.kodi_helper = None
        self.base_data_path = nx_common.data_path
        self.enable_custom_library_folder = enable_custom_folder
        self.custom_library_folder = nx_common.get_setting('customlibraryfolder')
        self.db_filepath = os.path.join(self.base_data_path, self.db_filename)
        self.log = nx_common.log

        # check for local library folder & set up the paths
        if self.enable_custom_library_folder != 'true':
            lib_path = self.base_data_path
        else:
            lib_path = self.custom_library_folder
        self.movie_path = os.path.join(lib_path, self.movies_label)
        self.tvshow_path = os.path.join(lib_path, self.series_label)
        self.metadata_path = os.path.join(lib_path, self.metadata_label)
        self.imagecache_path = os.path.join(lib_path, self.imagecache_label)

        # check if we need to setup the base folder structure & do so if needed
        self.setup_local_netflix_library(source={
            self.movies_label: self.movie_path,
            self.series_label: self.tvshow_path,
            self.metadata_label: self.metadata_path,
            self.imagecache_label: self.imagecache_path
        })

        # load the local db
        self.db = self._load_local_db(filename=self.db_filepath)

    def set_kodi_helper(self, kodi_helper):
        self.kodi_helper = kodi_helper

    def setup_local_netflix_library(self, source):
        """Sets up the basic directories

        Parameters
        ----------
        source : :obj:`dict` of :obj:`str`
            Dicitionary with directories to be created
        """
        for label in source:
            exists = xbmcvfs.exists(
                path=self.nx_common.check_folder_path(source[label]))
            if not exists:
                xbmcvfs.mkdir(source[label])

    def write_strm_file(self, path, url, title_player):
        """Writes the stream file that Kodi can use to integrate it into the DB

        Parameters
        ----------
        path : :obj:`str`
            Filepath of the file to be created

        url : :obj:`str`
            Stream url

        title_player : :obj:`str`
            Video fallback title for m3u

        """
        if isinstance(path, str):
            logpath = path.decode('ascii', 'ignore').encode('ascii')
        elif isinstance(path, unicode):
            logpath = path.encode('ascii', 'ignore')

        self.log('Writing {}'.format(logpath))

        f = xbmcvfs.File(path, 'w')
        f.write('#EXTINF:-1,'+title_player.encode('utf-8')+'\n')
        f.write(url)
        f.close()
        self.log('Successfully wrote {}'.format(logpath))

    def write_metadata_file(self, video_id, content):
        """Writes the metadata file that caches grabbed content from netflix

        Parameters
        ----------
        video_id : :obj:`str`
            ID of video

        content :
            Unchanged metadata from netflix
        """
        meta_file = os.path.join(self.metadata_path, video_id+'.meta')
        if not xbmcvfs.exists(meta_file):
            f = xbmcvfs.File(meta_file, 'wb')
            pickle.dump(content, f)
            f.close()

    def read_metadata_file(self, video_id):
        """Reads the metadata file that caches grabbed content from netflix

        Parameters
        ----------
        video_id : :obj:`str`
            ID of video

        content :
            Unchanged metadata from cache file
        """
        meta_file = os.path.join(self.metadata_path, str(video_id)+'.meta')
        if xbmcvfs.exists(meta_file):
            f = xbmcvfs.File(meta_file, 'rb')
            content = f.read()
            f.close()
            meta_data = pickle.loads(content)
            return meta_data
        return

    def read_artdata_file(self, video_id):
        """Reads the artdata file that caches grabbed content from netflix

        Parameters
        ----------
        video_id : :obj:`str`
            ID of video

        content :
            Unchanged artdata from cache file
        """
        meta_file = os.path.join(self.metadata_path, str(video_id)+'.art')
        if xbmcvfs.exists(meta_file):
            f = xbmcvfs.File(meta_file, 'rb')
            content = f.read()
            f.close()
            meta_data = pickle.loads(content)
            return meta_data
        return

    def write_artdata_file(self, video_id, content):
        """Writes the art data file that caches grabbed content from netflix

        Parameters
        ----------
        video_id : :obj:`str`
            ID of video

        content :
            Unchanged artdata from netflix
        """
        meta_file = os.path.join(self.metadata_path, video_id+'.art')
        if not xbmcvfs.exists(meta_file):
            f = xbmcvfs.File(meta_file, 'wb')
            pickle.dump(content, f)
            f.close()

    def _load_local_db(self, filename):
        """Loads the local db file and parses it, creates one if not existent

        Parameters
        ----------
        filename : :obj:`str`
            Filepath of db file

        Returns
        -------
        :obj:`dict`
            Parsed contents of the db file
        """
        # if the db doesn't exist, create it
        if not os.path.isfile(filename):
            data = {self.movies_label: {}, self.series_label: {}}
            self.log('Setup local library DB')
            self._update_local_db(filename=filename, db=data)
            return data

        with open(filename) as f:
            data = pickle.load(f)
            if data:
                return data
            else:
                return {}

    def _update_local_db(self, filename, db):
        """Updates the local db file with new data

        Parameters
        ----------
        filename : :obj:`str`
            Filepath of db file

        db : :obj:`dict`
            Database contents

        Returns
        -------
        bool
            Update has been successfully executed
        """
        if not os.path.isdir(os.path.dirname(filename)):
            return False
        with open(filename, 'w') as f:
            f.truncate()
            pickle.dump(db, f)
        return True

    def movie_exists(self, title, year):
        """Checks if a movie is already present in the local DB

        Parameters
        ----------
        title : :obj:`str`
            Title of the movie

        year : :obj:`int`
            Release year of the movie

        Returns
        -------
        bool
            Movie exists in DB
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        movie_meta = '%s (%d)' % (title, year)
        return movie_meta in self.db[self.movies_label]

    def show_exists(self, title):
        """Checks if a show is present in the local DB

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        Returns
        -------
        bool
            Show exists in DB
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        show_meta = '%s' % (title)
        return show_meta in self.db[self.series_label]

    def season_exists(self, title, season):
        """Checks if a season is present in the local DB

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        season : :obj:`int`
            Season sequence number

        Returns
        -------
        bool
            Season of show exists in DB
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        if self.show_exists(title) is False:
            return False
        show_entry = self.db[self.series_label][title]
        return season in show_entry['seasons']

    def episode_exists(self, title, season, episode):
        """Checks if an episode if a show is present in the local DB

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        season : :obj:`int`
            Season sequence number

        episode : :obj:`int`
            Episode sequence number

        Returns
        -------
        bool
            Episode of show exists in DB
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        if self.show_exists(title) is False:
            return False
        show_entry = self.db[self.series_label][title]
        episode_entry = 'S%02dE%02d' % (season, episode)
        return episode_entry in show_entry['episodes']

    def add_movie(self, title, alt_title, year, video_id, build_url):
        """Adds a movie to the local db, generates & persists the strm file

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        alt_title : :obj:`str`
            Alternative title given by the user

        year : :obj:`int`
            Release year of the show

        video_id : :obj:`str`
            ID of the video to be played

        build_url : :obj:`fn`
            Function to generate the stream url
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        movie_meta = '%s (%d)' % (title, year)
        folder = re.sub(r'[?|$|!|:|#]', r'', alt_title)
        dirname = self.nx_common.check_folder_path(
            path=os.path.join(self.movie_path, folder))
        filename = os.path.join(dirname, movie_meta + '.strm')
        progress = xbmcgui.DialogProgress()
        progress.create(self.kodi_helper.get_local_string(650), movie_meta)
        if xbmcvfs.exists(filename):
            return
        if not xbmcvfs.exists(dirname):
            xbmcvfs.mkdirs(dirname)
        if self.movie_exists(title=title, year=year) is False:
            progress.update(50)
            time.sleep(0.5)
            self.db[self.movies_label][movie_meta] = {'alt_title': alt_title}
            self._update_local_db(filename=self.db_filepath, db=self.db)
        url = build_url({'action': 'play_video', 'video_id': video_id})
        self.write_strm_file(path=filename, url=url, title_player=movie_meta)
        progress.update(100)
        time.sleep(1)
        progress.close()

    def add_show(self, netflix_id, title, alt_title, episodes, build_url,
                 in_background=False):
        """Adds a show to the local db, generates & persists the strm files

        Note: Can also used to store complete seasons or single episodes,
        it all depends on what is present in the episodes dictionary

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        alt_title : :obj:`str`
            Alternative title given by the user

        episodes : :obj:`dict` of :obj:`dict`
            Episodes that need to be added

        build_url : :obj:`fn`
            Function to generate the stream url
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        show_meta = '%s' % (title)
        folder = re.sub(r'[?|$|!|:|#]', r'', alt_title.encode('utf-8'))
        show_dir = self.nx_common.check_folder_path(
            path=os.path.join(self.tvshow_path, folder))
        progress = self._create_progress_dialog(in_background)
        progress.create(self.kodi_helper.get_local_string(650), show_meta)
        if not xbmcvfs.exists(show_dir):
            self.log('Created show folder {}'.format(show_dir))
            xbmcvfs.mkdirs(show_dir)
        if self.show_exists(title) is False:
            self.log('Show does not exists, adding entry to internal library')
            self.db[self.series_label][show_meta] = {
                'netflix_id': netflix_id,
                'seasons': [],
                'episodes': [],
                'alt_title': alt_title}
        else:
            self.log('Show is present in internal library: {}'
                     .format(self.db[self.series_label][show_meta]))
        if 'netflix_id' not in self.db[self.series_label][show_meta]:
            self.db[self.series_label][show_meta]['netflix_id'] = netflix_id
            self._update_local_db(filename=self.db_filepath, db=self.db)
            self.log('Added missing netflix_id={} for {} to internal library.'
                     .format(netflix_id, title.encode('utf-8')),
                     xbmc.LOGNOTICE)
        episodes = [episode for episode in episodes
                    if not self.episode_exists(title, episode['season'],
                                               episode['episode'])]
        self.log('Episodes to export: {}'.format(episodes))
        if len(episodes) == 0:
            self.log('No episodes to export, exiting')
            return False
        step = round(100.0 / len(episodes), 1)
        percent = step
        for episode in episodes:
            desc = self.kodi_helper.get_local_string(20373) + ': '
            desc += str(episode.get('season'))
            long_desc = self.kodi_helper.get_local_string(20359) + ': '
            long_desc += str(episode.get('episode'))
            progress.update(
                percent=int(percent),
                line1=show_meta,
                line2=desc,
                line3=long_desc)
            self._add_episode(
                show_dir=show_dir,
                title=title,
                season=episode.get('season'),
                episode=episode.get('episode'),
                video_id=episode.get('id'),
                build_url=build_url)
            percent += step
            time.sleep(0.05)
        self._update_local_db(filename=self.db_filepath, db=self.db)
        time.sleep(1)
        progress.close()
        if in_background:
            self.kodi_helper.dialogs.show_episodes_added_notify(
                title, len(episodes), self.kodi_helper.icon)
        return show_dir

    def _create_progress_dialog(self, is_noop):
        if is_noop:
            class NoopDialog():
                def create(self, title, subtitle):
                    return noop()

                def update(self, **kwargs):
                    return noop()

                def close(self):
                    return noop()

            return NoopDialog()
        return xbmcgui.DialogProgress()

    def _add_episode(self, title, show_dir, season, episode, video_id, build_url):
        """
        Adds a single episode to the local DB,
        generates & persists the strm file

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        show_dir : :obj:`str`
            Directory that holds the stream files for that show

        season : :obj:`int`
            Season sequence number

        episode : :obj:`int`
            Episode sequence number

        video_id : :obj:`str`
            ID of the video to be played

        build_url : :obj:`fn`
            Function to generate the stream url
        """
        season = int(season)
        episode = int(episode)
        title = re.sub(r'[?|$|!|:|#]', r'', title)

        self.log('Adding S{}E{} (id={}) of {} (dest={})'
                 .format(season, episode, video_id, title.encode('utf-8'),
                         show_dir))

        # add season
        if self.season_exists(title=title, season=season) is False:
            self.log(
                'Season {} does not exist, adding entry to internal library.'
                .format(season))
            self.db[self.series_label][title]['seasons'].append(season)

        # add episode
        episode_meta = 'S%02dE%02d' % (season, episode)
        episode_exists = self.episode_exists(
            title=title,
            season=season,
            episode=episode)
        if episode_exists is False:
            self.log(
                'S{}E{} does not exist, adding entry to internal library.'
                .format(season, episode))
            self.db[self.series_label][title]['episodes'].append(episode_meta)

        # create strm file
        filename = episode_meta + '.strm'
        filepath = os.path.join(show_dir, filename)
        if xbmcvfs.exists(filepath):
            self.log('strm file {} already exists, not writing it'
                     .format(filepath))
            return
        url = build_url({'action': 'play_video', 'video_id': video_id})
        self.write_strm_file(
            path=filepath,
            url=url,
            title_player=title + ' - ' + episode_meta)

    def remove_movie(self, title, year):
        """Removes the DB entry & the strm file for the movie given

        Parameters
        ----------
        title : :obj:`str`
            Title of the movie

        year : :obj:`int`
            Release year of the movie

        Returns
        -------
        bool
            Delete successfull
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        movie_meta = '%s (%d)' % (title, year)
        folder = re.sub(
            pattern=r'[?|$|!|:|#]',
            repl=r'',
            string=self.db[self.movies_label][movie_meta]['alt_title'])
        progress = xbmcgui.DialogProgress()
        progress.create(self.kodi_helper.get_local_string(1210), movie_meta)
        progress.update(50)
        time.sleep(0.5)
        del self.db[self.movies_label][movie_meta]
        self._update_local_db(filename=self.db_filepath, db=self.db)
        dirname = self.nx_common.check_folder_path(
            path=os.path.join(self.movie_path, folder))
        filename = os.path.join(self.movie_path, folder, movie_meta + '.strm')
        if xbmcvfs.exists(dirname):
            xbmcvfs.delete(filename)
            xbmcvfs.rmdir(dirname)
            return True
        return False
        time.sleep(1)
        progress.close()

    def remove_show(self, title):
        """Removes the DB entry & the strm files for the show given

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        Returns
        -------
        bool
            Delete successfull
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        label = self.series_label
        rep_str = self.db[label][title]['alt_title'].encode('utf-8')
        folder = re.sub(
            pattern=r'[?|$|!|:|#]',
            repl=r'',
            string=rep_str)
        progress = xbmcgui.DialogProgress()
        progress.create(self.kodi_helper.get_local_string(1210), title)
        time.sleep(0.5)
        del self.db[self.series_label][title]
        self._update_local_db(filename=self.db_filepath, db=self.db)
        show_dir = self.nx_common.check_folder_path(
            path=os.path.join(self.tvshow_path, folder))
        if xbmcvfs.exists(show_dir):
            show_files = xbmcvfs.listdir(show_dir)[1]
            episode_count_total = len(show_files)
            step = round(100.0 / episode_count_total, 1)
            percent = 100 - step
            for filename in show_files:
                progress.update(int(percent))
                xbmcvfs.delete(os.path.join(show_dir, filename))
                percent = percent - step
                time.sleep(0.05)
            xbmcvfs.rmdir(show_dir)
            return True
        return False
        time.sleep(1)
        progress.close()

    def remove_season(self, title, season):
        """Removes the DB entry & the strm files for a season of a show given

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        season : :obj:`int`
            Season sequence number

        Returns
        -------
        bool
            Delete successfull
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title.encode('utf-8'))
        season = int(season)
        season_list = []
        episodes_list = []
        show_meta = '%s' % (title)
        for season_entry in self.db[self.series_label][show_meta]['seasons']:
            if season_entry != season:
                season_list.append(season_entry)
        self.db[self.series_label][show_meta]['seasons'] = season_list
        alt_title = self.db[self.series_label][show_meta]['alt_title']
        show_dir = self.nx_common.check_folder_path(
            path=os.path.join(self.tvshow_path, alt_title))
        if xbmcvfs.exists(show_dir):
            show_files = [f for f in xbmcvfs.listdir(show_dir) if xbmcvfs.exists(os.path.join(show_dir, f))]
            for filename in show_files:
                if 'S%02dE' % (season) in filename:
                    xbmcvfs.delete(os.path.join(show_dir, filename))
                else:
                    episodes_list.append(filename.replace('.strm', ''))
            self.db[self.series_label][show_meta]['episodes'] = episodes_list
        self._update_local_db(filename=self.db_filepath, db=self.db)
        return True

    def remove_episode(self, title, season, episode):
        """Removes the DB entry & the strm files for an episode of a show given

        Parameters
        ----------
        title : :obj:`str`
            Title of the show

        season : :obj:`int`
            Season sequence number

        episode : :obj:`int`
            Episode sequence number

        Returns
        -------
        bool
            Delete successfull
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title.encode('utf-8'))
        episodes_list = []
        show_meta = '%s' % (title)
        episode_meta = 'S%02dE%02d' % (season, episode)
        alt_title = self.db[self.series_label][show_meta]['alt_title']
        show_dir = self.nx_common.check_folder_path(
            path=os.path.join(self.tvshow_path, alt_title))
        if xbmcvfs.exists(os.path.join(show_dir, episode_meta + '.strm')):
            xbmcvfs.delete(os.path.join(show_dir, episode_meta + '.strm'))
        for episode_entry in self.db[self.series_label][show_meta]['episodes']:
            if episode_meta != episode_entry:
                episodes_list.append(episode_entry)
        self.db[self.series_label][show_meta]['episodes'] = episodes_list
        self._update_local_db(filename=self.db_filepath, db=self.db)
        return True

    def list_exported_media(self):
        """Return List of exported movies

        Returns
        -------
        obj:`dict`
            Contents of export folder
        """
        movies = (['', ''])
        shows = (['', ''])
        movie_path = self.movie_path
        tvshow_path = self.tvshow_path
        if xbmcvfs.exists(self.nx_common.check_folder_path(movie_path)):
            movies = xbmcvfs.listdir(movie_path)
        if xbmcvfs.exists(self.nx_common.check_folder_path(tvshow_path)):
            shows = xbmcvfs.listdir(tvshow_path)
        return movies + shows

    def list_exported_shows(self):
        return self.db[self.series_label]

    def get_exported_movie_year(self, title):
        """Return year of given exported movie

        Returns
        -------
        obj:`int`
            year of given movie
        """
        year = '0000'
        folder = self.nx_common.check_folder_path(
            path=os.path.join(self.movie_path, title))
        if xbmcvfs.exists(folder):
            file = xbmcvfs.listdir(folder)
            year = str(file[1]).split('(', 1)[1].split(')', 1)[0]
        return int(year)

    def updatedb_from_exported(self):
        """Adds movies and shows from exported media to the local db

        Returns
        -------
        bool
            Process finished
        """
        tv_show_path = self.tvshow_path
        db_filepath = self.db_filepath
        if xbmcvfs.exists(self.nx_common.check_folder_path(self.movie_path)):
            movies = xbmcvfs.listdir(self.movie_path)
            for video in movies[0]:
                folder = os.path.join(self.movie_path, video)
                file = xbmcvfs.listdir(folder)
                year = int(str(file[1]).split("(", 1)[1].split(")", 1)[0])
                alt_title = unicode(video.decode('utf-8'))
                title = unicode(video.decode('utf-8'))
                movie_meta = '%s (%d)' % (title, year)
                if self.movie_exists(title=title, year=year) is False:
                    self.db[self.movies_label][movie_meta] = {
                        'alt_title': alt_title}
                    self._update_local_db(filename=db_filepath, db=self.db)

        if xbmcvfs.exists(self.nx_common.check_folder_path(tv_show_path)):
            shows = xbmcvfs.listdir(tv_show_path)
            for video in shows[0]:
                show_dir = os.path.join(tv_show_path, video)
                title = unicode(video.decode('utf-8'))
                alt_title = unicode(video.decode('utf-8'))
                show_meta = '%s' % (title)
                if self.show_exists(title) is False:
                    self.db[self.series_label][show_meta] = {
                        'seasons': [],
                        'episodes': [],
                        'alt_title': alt_title}
                    episodes = xbmcvfs.listdir(show_dir)
                    for episode in episodes[1]:
                        file = str(episode).split(".")[0]
                        season = int(str(file).split("S")[1].split("E")[0])
                        episode = int(str(file).split("E")[1])
                        episode_meta = 'S%02dE%02d' % (season, episode)
                        episode_exists = self.episode_exists(
                            title=title,
                            season=season,
                            episode=episode)
                        if episode_exists is False:
                            self.db[self.series_label][title]['episodes'].append(episode_meta)
                            self._update_local_db(
                                filename=self.db_filepath,
                                db=self.db)
        return True

    def download_image_file(self, title, url):
        """Writes thumb image which is shown in exported

        Parameters
        ----------
        title : :obj:`str`
            Filename based on title

        url : :obj:`str`
            Image url

        Returns
        -------
        bool
            Download triggered
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        imgfile = title + '.jpg'
        file = os.path.join(self.imagecache_path, imgfile)
        folder_movies = self.nx_common.check_folder_path(
            path=os.path.join(self.movie_path, title))
        folder_tvshows = self.nx_common.check_folder_path(
            path=os.path.join(self.tvshow_path, title))
        file_exists = xbmcvfs.exists(file)
        folder_exists = xbmcvfs.exists(folder_movies)
        tv_shows_folder = xbmcvfs.exists(folder_tvshows)
        if not file_exists and (folder_exists or tv_shows_folder):
            thread = threading.Thread(target=self.fetch_url, args=(url, file))
            thread.start()
        return True

    def fetch_url(self, url, file):
        f = xbmcvfs.File(file, 'wb')
        f.write(requests.get(url).content)
        f.write(url)
        f.close()

    def get_previewimage(self, title):
        """Load thumb image which is shown in exported

        Parameters
        ----------
        title : :obj:`str`
            Filename based on title

        url : :obj:`str`
            Image url

        Returns
        -------
        obj:`int`
            image of given title if exists
        """
        title = re.sub(r'[?|$|!|:|#]', r'', title)
        imgfile = title + '.jpg'
        file = os.path.join(self.imagecache_path, imgfile)
        if xbmcvfs.exists(file):
            return file
        return ""
