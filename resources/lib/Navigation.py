#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: Navigation
# Created on: 13.01.2017

import urllib
import urllib2
import json
import ast
import xbmc
from xbmcaddon import Addon
import resources.lib.NetflixSession as Netflix
from urlparse import parse_qsl,urlparse
from utils import noop, log

class Navigation:
    """Routes to the correct subfolder, dispatches actions & acts as a controller for the Kodi view & the Netflix model"""

    def __init__ (self, kodi_helper, library, base_url, log_fn=noop):
        """Takes the instances & configuration options needed to drive the plugin

        Parameters
        ----------
        kodi_helper : :obj:`KodiHelper`
            instance of the KodiHelper class

        library : :obj:`Library`
            instance of the Library class

        base_url : :obj:`str`
            plugin base url

        log_fn : :obj:`fn`
             optional log function
        """
        self.kodi_helper = kodi_helper
        self.library = library
        self.base_url = base_url
        self.log = log_fn

    @log
    def router (self, paramstring):
        """Route to the requested subfolder & dispatch actions along the way

        Parameters
        ----------
        paramstring : :obj:`str`
            Url query params
        """
        params = self.parse_paramters(paramstring=paramstring)

        # open foreign settings dialog
        if 'mode' in params.keys() and params['mode'] == 'openSettings':
            return self.open_settings(params['url'])

        # log out the user
        if 'action' in params.keys() and params['action'] == 'logout':
            return self.call_netflix_service({'method': 'logout'})

        # check login & try to relogin if necessary
        account = self.kodi_helper.get_credentials()
        if account['email'] != '' and account['password'] != '':
            if self.call_netflix_service({'method': 'is_logged_in'}) != True:
                if self.establish_session(account=account) != True:
                    return self.kodi_helper.show_login_failed_notification()

        # check if we need to execute any actions before the actual routing
        # gives back a dict of options routes might need
        options = self.before_routing_action(params=params)

        # check if one of the before routing options decided to killthe routing
        if 'exit' in options:
            self.kodi_helper.log("exit in options")
            return False
        if 'action' not in params.keys():
            # show the profiles
            return self.show_profiles()
        elif params['action'] == 'video_lists':
            # list lists that contain other lists (starting point with recommendations, search, etc.)
            return self.show_video_lists()
        elif params['action'] == 'video_list':
            # show a list of shows/movies
            type = None if 'type' not in params.keys() else params['type']
            start = 0 if 'start' not in params.keys() else int(params['start'])
            return self.show_video_list(video_list_id=params['video_list_id'], type=type, start=start)
        elif params['action'] == 'season_list':
            # list of seasons for a show
            return self.show_seasons(show_id=params['show_id'], tvshowtitle=params['tvshowtitle'])
        elif params['action'] == 'episode_list':
            # list of episodes for a season
            return self.show_episode_list(season_id=params['season_id'], tvshowtitle=params['tvshowtitle'])
        elif params['action'] == 'rating':
            return self.rate_on_netflix(video_id=params['id'])
        elif params['action'] == 'remove_from_list':
            # removes a title from the users list on Netflix
            self.kodi_helper.invalidate_memcache()
            return self.remove_from_list(video_id=params['id'])
        elif params['action'] == 'add_to_list':
            # adds a title to the users list on Netflix
            self.kodi_helper.invalidate_memcache()
            return self.add_to_list(video_id=params['id'])
        elif params['action'] == 'export':
            # adds a title to the users list on Netflix
            alt_title = self.kodi_helper.show_add_to_library_title_dialog(original_title=urllib.unquote(params['title']).decode('utf8'))
            return self.export_to_library(video_id=params['id'], alt_title=alt_title)
        elif params['action'] == 'remove':
            # adds a title to the users list on Netflix
            return self.remove_from_library(video_id=params['id'])
        elif params['action'] == 'removeexported':
            # adds a title to the users list on Netflix
            term = self.kodi_helper.show_finally_remove(title=params['title'], type=params['type'], year=params['year'])
            if params['type'] == 'movie' and str(term) == '1':
                self.library.remove_movie(title=params['title'].decode('utf-8'), year=int(params['year']))
                self.kodi_helper.refresh()
            if params['type'] == 'show' and str(term) == '1':
                self.library.remove_show(title=params['title'].decode('utf-8'))
                self.kodi_helper.refresh()
            return True
        elif params['action'] == 'updatedb':
            # adds a title to the users list on Netflix
            self.library.updatedb_from_exported()
            self.kodi_helper.show_local_db_updated()
            return True
        elif params['action'] == 'user-items' and params['type'] != 'search' and params['type'] != 'exported':
            # display the lists (recommendations, genres, etc.)
            return self.show_user_list(type=params['type'])
        elif params['action'] == 'play_video':
            self.play_video(video_id=params['video_id'], start_offset=params.get('start_offset', -1), infoLabels=params.get('infoLabels', {}))
        elif params['action'] == 'user-items' and params['type'] == 'search':
            # if the user requested a search, ask for the term
            term = self.kodi_helper.show_search_term_dialog()
            return self.show_search_results(term=term) or False
        elif params['action'] == 'user-items' and params['type'] == 'exported':
            # update local db from exported media
            self.library.updatedb_from_exported()
            # list exported movies/shows
            return self.kodi_helper.build_video_listing_exported(content=self.library.list_exported_media(),build_url=self.build_url)
        else:
            raise ValueError('Invalid paramstring: {0}!'.format(paramstring))
        xbmc.executebuiltin('Container.Refresh')
        return True

    @log
    def play_video (self, video_id, start_offset, infoLabels):
        """Starts video playback

        Note: This is just a dummy, inputstream is needed to play the vids

        Parameters
        ----------
        video_id : :obj:`str`
            ID of the video that should be played

        start_offset : :obj:`str`
            Offset to resume playback from (in seconds)

        infoLabels : :obj:`str`
            the listitem's infoLabels
        """
        try:
            infoLabels = ast.literal_eval(infoLabels)
        except:
            infoLabels= {}
        esn = self.call_netflix_service({'method': 'get_esn'})
        return self.kodi_helper.play_item(esn=esn, video_id=video_id, start_offset=start_offset, infoLabels=infoLabels)

    @log
    def show_search_results (self, term):
        """Display a list of search results

        Parameters
        ----------
        term : :obj:`str`
            String to lookup

        Returns
        -------
        bool
            If no results are available
        """
        user_data = self.call_netflix_service({'method': 'get_user_data'})
        search_contents = self.call_netflix_service({'method': 'search', 'term': term, 'guid': user_data['guid'], 'cache': True})
        # check for any errors
        if self._is_dirty_response(response=search_contents) or len(search_contents) == 0:
            self.kodi_helper.show_no_search_results_notification()
            return False
        actions = {'movie': 'play_video', 'show': 'season_list'}
        return self.kodi_helper.build_search_result_listing(video_list=search_contents, actions=actions, build_url=self.build_url)

    def show_user_list (self, type):
        """List the users lists for shows/movies for recommendations/genres based on the given type

        Parameters
        ----------
        user_list_id : :obj:`str`
            Type of list to display
        """
        # determine if weÂ´re in kids mode
        user_data = self.call_netflix_service({'method': 'get_user_data'})
        video_list_ids = self.call_netflix_service({'method': 'fetch_video_list_ids', 'guid': user_data['guid'], 'cache': True})
        # check for any errors
        if self._is_dirty_response(response=video_list_ids):
            return False
        return self.kodi_helper.build_user_sub_listing(video_list_ids=video_list_ids[type], type=type, action='video_list', build_url=self.build_url)

    def show_episode_list (self, season_id, tvshowtitle):
        """Lists all episodes for a given season

        Parameters
        ----------
        season_id : :obj:`str`
            ID of the season episodes should be displayed for

        tvshowtitle : :obj:`str`
            title of the show (for listitems' infolabels)
        """
        user_data = self.call_netflix_service({'method': 'get_user_data'})
        episode_list = self.call_netflix_service({'method': 'fetch_episodes_by_season', 'season_id': season_id, 'guid': user_data['guid'], 'cache': True})
        # check for any errors
        if self._is_dirty_response(response=episode_list):
            return False

        # Extract episode numbers and associated keys.
        d = [(v['episode'], k) for k, v in episode_list.items()]

        # sort episodes by number (theyÂ´re coming back unsorted from the api)
        episodes_sorted = [episode_list[k] for (_, k) in sorted(d)]

        for episode in episodes_sorted:
            episode['tvshowtitle'] = tvshowtitle

        # list the episodes
        return self.kodi_helper.build_episode_listing(episodes_sorted=episodes_sorted, build_url=self.build_url)

    def show_seasons (self, show_id, tvshowtitle):
        """Lists all seasons for a given show

        Parameters
        ----------
        show_id : :obj:`str`
            ID of the show seasons should be displayed for

        tvshowtitle : :obj:`str`
            title of the show (for listitems' infolabels)
        Returns
        -------
        bool
            If no seasons are available
        """
        user_data = self.call_netflix_service({'method': 'get_user_data'})
        season_list = self.call_netflix_service({'method': 'fetch_seasons_for_show', 'show_id': show_id, 'guid': user_data['guid'], 'cache': True})
        # check for any errors
        if self._is_dirty_response(response=season_list):
            return False
        # check if we have sesons, announced shows that are not available yet have none
        if len(season_list) == 0:
            return self.kodi_helper.build_no_seasons_available()

        # Extract episode numbers and associated keys.
        d = [(v['idx'], k) for k, v in season_list.items()]

        # sort seasons by index by default (theyÂ´re coming back unsorted from the api)
        seasons_sorted = [season_list[k] for (_, k) in sorted(d)]

        for season in seasons_sorted:
            season['tvshowtitle'] = tvshowtitle

        return self.kodi_helper.build_season_listing(seasons_sorted=seasons_sorted, build_url=self.build_url)

    def show_video_list (self, video_list_id, type, start=0):
        """List shows/movies based on the given video list id

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed

        type : :obj:`str`
            None or 'queue' f.e. when itÂ´s a special video lists

        start : :obj:`int`
            Starting point
        """
        end = start + Netflix.FETCH_VIDEO_REQUEST_COUNT
        video_list = {}
        user_data = self.call_netflix_service({'method': 'get_user_data'})

        for i in range(0,4):
            items = self.call_netflix_service({'method': 'fetch_video_list', 'list_id': video_list_id, 'list_from':start, 'list_to':end, 'guid': user_data['guid'] ,'cache': True})
            if self._is_dirty_response(response=items) and i == 0:
                self.kodi_helper.log("show_video_list response is dirty")
                return False
            elif len(items) == 0:
                if i == 0:
                    self.kodi_helper.log("show_video_list items=0")
                    return False
                break
            video_list.update(items)
            start=end+1
            end=start+Netflix.FETCH_VIDEO_REQUEST_COUNT
        has_more = len(video_list) == (Netflix.FETCH_VIDEO_REQUEST_COUNT + 1) * 4
        actions = {'movie': 'play_video', 'show': 'season_list'}
        return self.kodi_helper.build_video_listing(video_list=video_list, actions=actions, type=type, build_url=self.build_url, has_more=has_more, start=start, current_video_list_id=video_list_id)

    def show_video_lists (self):
        """List the users video lists (recommendations, my list, etc.)"""
        user_data = self.call_netflix_service({'method': 'get_user_data'})
        video_list_ids = self.call_netflix_service({'method': 'fetch_video_list_ids', 'guid': user_data['guid'], 'cache': True})
        # check for any errors
        if self._is_dirty_response(response=video_list_ids):
            return False
        # defines an order for the user list, as Netflix changes the order at every request
        user_list_order = ['queue', 'continueWatching', 'topTen', 'netflixOriginals', 'trendingNow', 'newRelease', 'popularTitles']
        # define where to route the user
        actions = {'recommendations': 'user-items', 'genres': 'user-items', 'search': 'user-items', 'exported': 'user-items', 'default': 'video_list'}
        return self.kodi_helper.build_main_menu_listing(video_list_ids=video_list_ids, user_list_order=user_list_order, actions=actions, build_url=self.build_url)

    @log
    def show_profiles (self):
        """List the profiles for the active account"""
        profiles = self.call_netflix_service({'method': 'list_profiles'})
        if len(profiles) == 0:
            return self.kodi_helper.show_login_failed_notification()
        return self.kodi_helper.build_profiles_listing(profiles=profiles.values(), action='video_lists', build_url=self.build_url)

    @log
    def rate_on_netflix (self, video_id):
        """Rate a show/movie/season/episode on Netflix

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed
        """
        rating = self.kodi_helper.show_rating_dialog()
        return self.call_netflix_service({'method': 'rate_video', 'video_id': video_id, 'rating': rating})

    @log
    def remove_from_list (self, video_id):
        """Remove an item from 'My List' & refresh the view

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed
        """
        self.call_netflix_service({'method': 'remove_from_list', 'video_id': video_id})
        return self.kodi_helper.refresh()

    @log
    def add_to_list (self, video_id):
        """Add an item to 'My List' & refresh the view

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed
        """
        self.call_netflix_service({'method': 'add_to_list', 'video_id': video_id})
        return self.kodi_helper.refresh()

    @log
    def export_to_library (self, video_id, alt_title):
        """Adds an item to the local library

        Parameters
        ----------
        video_id : :obj:`str`
            ID of the movie or show

        alt_title : :obj:`str`
            Alternative title (for the folder written to disc)
        """
        metadata = self.call_netflix_service({'method': 'fetch_metadata', 'video_id': video_id})
        if "error" in metadata:
            self.kodi_helper.show_no_metadata_notification()
            return False
        # check for any errors
        if self._is_dirty_response(response=metadata):
            return False
        video = metadata['video']

        if video['type'] == 'movie':
            self.library.add_movie(title=video['title'], alt_title=alt_title, year=video['year'], video_id=video_id, build_url=self.build_url)
        if video['type'] == 'show':
            episodes = []
            for season in video['seasons']:
                for episode in season['episodes']:
                    episodes.append({'season': season['seq'], 'episode': episode['seq'], 'id': episode['id']})

            self.library.add_show(title=video['title'], alt_title=alt_title, episodes=episodes, build_url=self.build_url)
        return self.kodi_helper.refresh()

    @log
    def remove_from_library (self, video_id, season=None, episode=None):
        """Removes an item from the local library

        Parameters
        ---------
        video_id : :obj:`str`
            ID of the movie or show
        """
        metadata = self.call_netflix_service({'method': 'fetch_metadata', 'video_id': video_id})
        if "error" in metadata:
            self.kodi_helper.show_no_metadata_notification()
            return False
        # check for any errors
        if self._is_dirty_response(response=metadata):
            return False
        video = metadata['video']

        if video['type'] == 'movie':
            self.library.remove_movie(title=video['title'], year=video['year'])
        if video['type'] == 'show':
            self.library.remove_show(title=video['title'])
        return self.kodi_helper.refresh()

    @log
    def establish_session(self, account):
        """Checks if we have an cookie with an active sessions, otherwise tries to login the user

        Parameters
        ----------
        account : :obj:`dict` of :obj:`str`
            Dict containing an email & a password property

        Returns
        -------
        bool
            If we don't have an active session & the user couldn't be logged in
        """
        is_logged_in = self.call_netflix_service({'method': 'is_logged_in'})
        return True if is_logged_in else self.call_netflix_service({'method': 'login', 'email': account['email'], 'password': account['password']})

    @log
    def before_routing_action (self, params):
        """Executes actions before the actual routing takes place:

            - Check if account data has been stored, if not, asks for it
            - Check if the profile should be changed (and changes if so)
            - Establishes a session if no action route is given

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Url query params

        Returns
        -------
        :obj:`dict` of :obj:`str`
            Options that can be provided by this hook & used later in the routing process
        """
        options = {}
        credentials = self.kodi_helper.get_credentials()
        # check if we have user settings, if not, set em
        if credentials['email'] == '':
            email = self.kodi_helper.show_email_dialog()
            self.kodi_helper.set_setting(key='email', value=email)
            credentials['email'] = email
        if credentials['password'] == '':
            password = self.kodi_helper.show_password_dialog()
            self.kodi_helper.set_setting(key='password', value=password)
            credentials['password'] = password
        # persist & load main menu selection
        if 'type' in params:
            self.kodi_helper.set_main_menu_selection(type=params['type'])
        options['main_menu_selection'] = self.kodi_helper.get_main_menu_selection()
        # check and switch the profile if needed
        if self.check_for_designated_profile_change(params=params):
            self.kodi_helper.invalidate_memcache()
            profile_id = params.get('profile_id', None)
            if profile_id == None:
                user_data = self.call_netflix_service({'method': 'get_user_data'})
                profile_id = user_data['guid']
            self.call_netflix_service({'method': 'switch_profile', 'profile_id': profile_id})
        # check login, in case of main menu
        if 'action' not in params:
            self.establish_session(account=credentials)
        return options

    def check_for_designated_profile_change (self, params):
        """Checks if the profile needs to be switched

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Url query params

        Returns
        -------
        bool
            Profile should be switched or not
        """
        # check if we need to switch the user
        user_data = self.call_netflix_service({'method': 'get_user_data'})
        profiles = self.call_netflix_service({'method': 'list_profiles'})
        if 'guid' not in user_data:
            return False
        current_profile_id = user_data['guid']
        if profiles.get(current_profile_id).get('isKids', False) == True:
            return True
        return 'profile_id' in params and current_profile_id != params['profile_id']

    def parse_paramters (self, paramstring):
        """Tiny helper to convert a url paramstring into a dictionary

        Parameters
        ----------
        paramstring : :obj:`str`
            Url query params (in url string notation)

        Returns
        -------
        :obj:`dict` of :obj:`str`
            Url query params (as a dictionary)
        """
        return dict(parse_qsl(paramstring))

    def _is_expired_session (self, response):
        """Checks if a response error is based on an invalid session

        Parameters
        ----------
        response : :obj:`dict` of :obj:`str`
            Error response object

        Returns
        -------
        bool
            Error is based on an invalid session
        """
        return 'error' in response and 'code' in response and str(response['code']) == '401'

    def _is_dirty_response (self, response):
        """Checks if a response contains an error & if the error is based on an invalid session, it tries a relogin

        Parameters
        ----------
        response : :obj:`dict` of :obj:`str`
            Success response object or Error response object

        Returns
        -------
        bool
            Response contains error or not
        """
        # check for any errors
        if 'error' in response:
            # check if we do not have a valid session, in case that happens: (re)login
            if self._is_expired_session(response=response):
                if self.establish_session(account=self.kodi_helper.get_credentials()):
                    return True
            message = response['message'] if 'message' in response else ''
            code = response['code'] if 'code' in response else ''
            self.log(msg='[ERROR]: ' + message + '::' + str(code))
            return True
        return False

    def build_url(self, query):
        """Tiny helper to transform a dict into a url + querystring

        Parameters
        ----------
        query : :obj:`dict` of  :obj:`str`
            List of paramters to be url encoded

        Returns
        -------
        str
            Url + querystring based on the param
        """
        return self.base_url + '?' + urllib.urlencode(query)

    def get_netflix_service_url (self):
        """Returns URL & Port of the internal Netflix HTTP Proxy service

        Returns
        -------
        str
            Url + Port
        """
        return 'http://127.0.0.1:' + str(self.kodi_helper.get_addon().getSetting('netflix_service_port'))

    def call_netflix_service (self, params):
        """Makes a GET request to the internal Netflix HTTP proxy and returns the result

        Parameters
        ----------
        params : :obj:`dict` of  :obj:`str`
            List of paramters to be url encoded

        Returns
        -------
        :obj:`dict`
            Netflix Service RPC result
        """
        url_values = urllib.urlencode(params)
        # check for cached items
        if params.get('cache', False) == True:
            cached_value = self.kodi_helper.get_cached_item(cache_id=url_values)

            # Cache lookup successful?
            if cached_value != None:
                self.log(msg='Fetched item from cache: (cache_id=' + url_values + ')')
                return cached_value

        url = self.get_netflix_service_url()
        full_url = url + '?' + url_values
        # don't use proxy for localhost
        if (urlparse(url).hostname in ('localhost','127.0.0.1','::1')):
            urllib2.install_opener(urllib2.build_opener(urllib2.ProxyHandler({})))
        data = urllib2.urlopen(full_url).read()
        parsed_json = json.loads(data)
        result = parsed_json.get('result', None)
        if params.get('cache', False) == True:
            self.log(msg='Adding item to cache: (cache_id=' + url_values + ')')
            self.kodi_helper.add_cached_item(cache_id=url_values, contents=result)
        return result

    def open_settings(self, url):
        """Opens a foreign settings dialog"""
        (is_addon, _) = self.kodi_helper.get_inputstream_addon()
        url = is_addon if url == 'is' else url
        return Addon(url).openSettings()
