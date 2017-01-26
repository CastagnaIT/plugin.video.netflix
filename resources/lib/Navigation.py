#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: Navigation
# Created on: 13.01.2017

import urllib
import time
from urlparse import parse_qsl
from utils import noop
from utils import log

class Navigation:
    """Routes to the correct subfolder, dispatches actions & acts as a controller for the Kodi view & the Netflix model"""

    def __init__ (self, netflix_session, kodi_helper, library, base_url, log_fn=noop):
        """Takes the instances & configuration options needed to drive the plugin

        Parameters
        ----------
        netflix_session : :obj:`NetflixSession`
            instance of the NetflixSession class

        kodi_helper : :obj:`KodiHelper`
            instance of the KodiHelper class

        library : :obj:`Library`
            instance of the Library class

        base_url : :obj:`str`
            plugin base url

        log_fn : :obj:`fn`
             optional log function
        """
        self.netflix_session = netflix_session
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

        # log out the user
        if 'action' in params.keys() and params['action'] == 'logout':
            return self.netflix_session.logout()

        # check login & try to relogin if necessary
        account = self.kodi_helper.get_credentials()
        if self.netflix_session.is_logged_in(account=account) != True:
            if self.establish_session(account=account) != True:
                return self.kodi_helper.show_login_failed_notification()

        # check if we need to execute any actions before the actual routing
        # gives back a dict of options routes might need
        options = self.before_routing_action(params=params)

        # check if one of the before routing options decided to killthe routing
        if 'exit' in options:
            return False
        if 'action' not in params.keys():
            # show the profiles
            self.show_profiles()
        elif params['action'] == 'video_lists':
            # list lists that contain other lists (starting point with recommendations, search, etc.)
            return self.show_video_lists()
        elif params['action'] == 'video_list':
            # show a list of shows/movies
            type = None if 'type' not in params.keys() else params['type']
            return self.show_video_list(video_list_id=params['video_list_id'], type=type)
        elif params['action'] == 'season_list':
            # list of seasons for a show
            return self.show_seasons(show_id=params['show_id'])
        elif params['action'] == 'episode_list':
            # list of episodes for a season
            return self.show_episode_list(season_id=params['season_id'])
        elif params['action'] == 'rating':
            return self.rate_on_netflix(video_id=params['id'])
        elif params['action'] == 'remove_from_list':
            # removes a title from the users list on Netflix
            return self.remove_from_list(video_id=params['id'])
        elif params['action'] == 'add_to_list':
            # adds a title to the users list on Netflix
            return self.add_to_list(video_id=params['id'])
        elif params['action'] == 'user-items' and params['type'] != 'search':
            # display the lists (recommendations, genres, etc.)
            return self.show_user_list(type=params['type'])
        elif params['action'] == 'play_video':
            # play a video, check for adult pin if needed
            adult_pin = None
            if self.check_for_adult_pin(params=params):
                adult_pin = self.kodi_helper.show_adult_pin_dialog()
                if self.netflix_session.send_adult_pin(adult_pin=adult_pin) != True:
                    return self.kodi_helper.show_wrong_adult_pin_notification()
            self.play_video(video_id=params['video_id'], start_offset=params['start_offset'])
        elif params['action'] == 'user-items' and params['type'] == 'search':
            # if the user requested a search, ask for the term
            term = self.kodi_helper.show_search_term_dialog()
            return self.show_search_results(term=term)
        else:
            raise ValueError('Invalid paramstring: {0}!'.format(paramstring))
        return True

    @log
    def play_video (self, video_id, start_offset):
        """Starts video playback

        Note: This is just a dummy, inputstream is needed to play the vids

        Parameters
        ----------
        video_id : :obj:`str`
            ID of the video that should be played

        start_offset : :obj:`str`
            Offset to resume playback from (in seconds)
        """
        # widevine esn
        esn = self.netflix_session.esn
        return self.kodi_helper.play_item(esn=esn, video_id=video_id, start_offset=start_offset)

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
        has_search_results = False
        search_results_raw = self.netflix_session.fetch_search_results(term=term)
        # check for any errors
        if self._is_dirty_response(response=search_results_raw):
            return False

        # determine if we found something
        if 'search' in search_results_raw['value']:
            for key in search_results_raw['value']['search'].keys():
                if self.netflix_session._is_size_key(key=key) == False:
                    has_search_results = search_results_raw['value']['search'][key]['titles']['length'] > 0

        # display that we haven't found a thing
        if has_search_results == False:
            return self.kodi_helper.build_no_search_results_available(build_url=self.build_url, action='search')

        # list the search results
        search_results = self.netflix_session.parse_search_results(response_data=search_results_raw)
        # add more menaingful data to the search results
        raw_search_contents = self.netflix_session.fetch_video_list_information(video_ids=search_results.keys())
        # check for any errors
        if self._is_dirty_response(response=raw_search_contents):
            return False
        search_contents = self.netflix_session.parse_video_list(response_data=raw_search_contents)
        actions = {'movie': 'play_video', 'show': 'season_list'}
        return self.kodi_helper.build_search_result_listing(video_list=search_contents, actions=actions, build_url=self.build_url)

    def show_user_list (self, type):
        """List the users lists for shows/movies for recommendations/genres based on the given type

        Parameters
        ----------
        user_list_id : :obj:`str`
            Type of list to display
        """
        video_list_ids_raw = self.netflix_session.fetch_video_list_ids()
        # check for any errors
        if self._is_dirty_response(response=video_list_ids_raw):
            return False
        video_list_ids = self.netflix_session.parse_video_list_ids(response_data=video_list_ids_raw)
        return self.kodi_helper.build_user_sub_listing(video_list_ids=video_list_ids[type], type=type, action='video_list', build_url=self.build_url)

    def show_episode_list (self, season_id):
        """Lists all episodes for a given season

        Parameters
        ----------
        season_id : :obj:`str`
            ID of the season episodes should be displayed for
        """
        raw_episode_list = self.netflix_session.fetch_episodes_by_season(season_id=season_id)
        # check for any errors
        if self._is_dirty_response(response=raw_episode_list):
            return False
        # parse the raw Netflix data
        episode_list = self.netflix_session.parse_episodes_by_season(response_data=raw_episode_list)

        # sort seasons by number (they´re coming back unsorted from the api)
        episodes_sorted = []
        for episode_id in episode_list:
            episodes_sorted.append(int(episode_list[episode_id]['episode']))
            episodes_sorted.sort()

        # list the episodes
        return self.kodi_helper.build_episode_listing(episodes_sorted=episodes_sorted, episode_list=episode_list, build_url=self.build_url)

    def show_seasons (self, show_id):
        """Lists all seasons for a given show

        Parameters
        ----------
        show_id : :obj:`str`
            ID of the show seasons should be displayed for

        Returns
        -------
        bool
            If no seasons are available
        """
        season_list_raw = self.netflix_session.fetch_seasons_for_show(id=show_id);
        # check for any errors
        if self._is_dirty_response(response=season_list_raw):
            return False
        # check if we have sesons, announced shows that are not available yet have none
        if 'seasons' not in season_list_raw['value']:
            return self.kodi_helper.build_no_seasons_available()
        # parse the seasons raw response from Netflix
        season_list = self.netflix_session.parse_seasons(id=show_id, response_data=season_list_raw)
        # sort seasons by index by default (they´re coming back unsorted from the api)
        seasons_sorted = []
        for season_id in season_list:
            seasons_sorted.append(int(season_list[season_id]['shortName'].split(' ')[1]))
            seasons_sorted.sort()
        return self.kodi_helper.build_season_listing(seasons_sorted=seasons_sorted, season_list=season_list, build_url=self.build_url)

    def show_video_list (self, video_list_id, type):
        """List shows/movies based on the given video list id

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed

        type : :obj:`str`
            None or 'queue' f.e. when it´s a special video lists
        """
        raw_video_list = self.netflix_session.fetch_video_list(list_id=video_list_id)
        # check for any errors
        if self._is_dirty_response(response=raw_video_list):
            return False
        # parse the video list ids
        video_list = self.netflix_session.parse_video_list(response_data=raw_video_list)
        actions = {'movie': 'play_video', 'show': 'season_list'}
        return self.kodi_helper.build_video_listing(video_list=video_list, actions=actions, type=type, build_url=self.build_url)

    def show_video_lists (self):
        """List the users video lists (recommendations, my list, etc.)"""
        # fetch video lists
        raw_video_list_ids = self.netflix_session.fetch_video_list_ids()
        # check for any errors
        if self._is_dirty_response(response=raw_video_list_ids):
            return False
        # parse the video list ids
        video_list_ids = self.netflix_session.parse_video_list_ids(response_data=raw_video_list_ids)
        # defines an order for the user list, as Netflix changes the order at every request
        user_list_order = ['queue', 'continueWatching', 'topTen', 'netflixOriginals', 'trendingNow', 'newRelease', 'popularTitles']
        # define where to route the user
        actions = {'recommendations': 'user-items', 'genres': 'user-items', 'search': 'user-items', 'default': 'video_list'}
        return self.kodi_helper.build_main_menu_listing(video_list_ids=video_list_ids, user_list_order=user_list_order, actions=actions, build_url=self.build_url)

    def show_profiles (self):
        """List the profiles for the active account"""
        self.netflix_session.refresh_session_data(account=self.kodi_helper.get_credentials())
        profiles = self.netflix_session.profiles
        return self.kodi_helper.build_profiles_listing(profiles=profiles, action='video_lists', build_url=self.build_url)

    @log
    def rate_on_netflix (self, video_id):
        """Rate a show/movie/season/episode on Netflix

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed
        """
        rating = self.kodi_helper.show_rating_dialog()
        return self.netflix_session.rate_video(video_id=video_id, rating=rating)

    @log
    def remove_from_list (self, video_id):
        """Remove an item from 'My List' & refresh the view

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed
        """
        self.netflix_session.remove_from_list(video_id=video_id)
        return self.kodi_helper.refresh()

    @log
    def add_to_list (self, video_id):
        """Add an item to 'My List' & refresh the view

        Parameters
        ----------
        video_list_id : :obj:`str`
            ID of the video list that should be displayed
        """
        self.netflix_session.add_to_list(video_id=video_id)
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
        if self.netflix_session.is_logged_in(account=account):
            return True
        else:
            return self.netflix_session.login(account=account)

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
        if credentials['password'] == '':
            password = self.kodi_helper.show_password_dialog()
            self.kodi_helper.set_setting(key='password', value=password)
        # persist & load main menu selection
        if 'type' in params:
            self.kodi_helper.set_main_menu_selection(type=params['type'])
        options['main_menu_selection'] = self.kodi_helper.get_main_menu_selection()
        # check and switch the profile if needed
        if self.check_for_designated_profile_change(params=params):
            self.netflix_session.switch_profile(profile_id=params['profile_id'], account=credentials)
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
        if 'guid' not in self.netflix_session.user_data:
            return False
        current_profile_id = self.netflix_session.user_data['guid']
        return 'profile_id' in params and current_profile_id != params['profile_id']

    def check_for_adult_pin (self, params):
        """Checks if an adult pin is given in the query params

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Url query params

        Returns
        -------
        bool
            Adult pin parameter exists or not
        """
        return (True, False)[params['pin'] == 'True']

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
            self.log(msg='[ERROR]: ' + response['message'] + '::' + str(response['code']))
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
