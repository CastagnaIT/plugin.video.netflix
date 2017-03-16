#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Module: NetflixHttpSubRessourceHandler
# Created on: 07.03.2017

from urllib2 import urlopen, URLError

class NetflixHttpSubRessourceHandler:
    """ Represents the callable internal server routes & translates/executes them to requests for Netflix"""

    def __init__ (self, kodi_helper, netflix_session):
        """Sets up credentials & video_list_cache cache
        Assigns the netflix_session/kodi_helper instacnes
        Does the initial login if we have user data

        Parameters
        ----------
        kodi_helper : :obj:`KodiHelper`
            instance of the KodiHelper class

        netflix_session : :obj:`NetflixSession`
            instance of the NetflixSession class
        """
        self.kodi_helper = kodi_helper
        self.netflix_session = netflix_session
        self.credentials = self.kodi_helper.get_credentials()
        self.profiles = []
        self.prefetch_login()
        self.video_list_cache = {}
        self.lolomo = None

    def prefetch_login (self):
        """Check if we have stored credentials.
        If so, do the login before the user requests it
        If that is done, we cache the profiles
        """
        if self._network_availble():
            if self.credentials['email'] != '' and self.credentials['password'] != '':
                if self.netflix_session.is_logged_in(account=self.credentials):
                    self.netflix_session.refresh_session_data(account=self.credentials)
                    self.profiles = self.netflix_session.profiles
                else:
                    self.netflix_session.login(account=self.credentials)
                    self.profiles = self.netflix_session.profiles
            else:
                self.profiles = []
        else:
            sleep(1)
            self.prefetch_login()

    def is_logged_in (self, params):
        """Existing login proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        if self.credentials['email'] == '' or self.credentials['password'] == '':
            return False
        return self.netflix_session.is_logged_in(account=self.credentials)

    def logout (self, params):
        """Logout proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        self.profiles = []
        self.credentials = {'email': '', 'password': ''}
        self.lolomo = None
        return self.netflix_session.logout()

    def login (self, params):
        """Logout proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        email = params.get('email', [''])[0]
        password = params.get('password', [''])[0]
        if email != '' and password != '':
            self.credentials = {'email': email, 'password': password}
            _ret = self.netflix_session.login(account=self.credentials)
            self.profiles = self.netflix_session.profiles
            return _ret
        return None

    def list_profiles (self, params):
        """Returns the cached list of profiles

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`dict` of :obj:`str`
            List of profiles
        """
        return self.profiles

    def get_esn (self, params):
        """ESN getter function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`str`
            Exracted ESN
        """
        return self.netflix_session.esn

    def fetch_video_list_ids (self, params):
        """Video list ids proxy function (caches video lists)

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`list`
            Transformed response of the remote call
        """
        cached_list = self.video_list_cache.get(self.netflix_session.user_data['guid'], None)
        if cached_list != None:
            self.kodi_helper.log('Serving cached list for user: ' + self.netflix_session.user_data['guid'])
            return cached_list
        video_list_ids_raw = self.netflix_session.fetch_video_list_ids()
        if 'error' in video_list_ids_raw:
            return video_list_ids_raw
        return self.netflix_session.parse_video_list_ids(response_data=video_list_ids_raw)

    def fetch_video_list_ids_for_kids (self, params):
        """Video list ids proxy function (thanks to Netflix that we need to use a different API for Kids profiles)

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`list`
            Transformed response of the remote call
        """
        if self.lolomo == None:
            self.lolomo = self.netflix_session.get_lolomo_for_kids()
        response = self.netflix_session.fetch_lists_for_kids(lolomo=self.lolomo)
        return response

    def fetch_video_list (self, params):
        """Video list proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`list`
            Transformed response of the remote call
        """
        list_id = params.get('list_id', [''])[0]
        raw_video_list = self.netflix_session.fetch_video_list(list_id=list_id)
        if 'error' in raw_video_list:
            return raw_video_list
        # parse the video list ids
        if 'videos' in raw_video_list.get('value', {}).keys():
            return self.netflix_session.parse_video_list(response_data=raw_video_list)
        return []

    def fetch_episodes_by_season (self, params):
        """Episodes for season proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`list`
            Transformed response of the remote call
        """
        raw_episode_list = self.netflix_session.fetch_episodes_by_season(season_id=params.get('season_id')[0])
        if 'error' in raw_episode_list:
            return raw_episode_list
        return self.netflix_session.parse_episodes_by_season(response_data=raw_episode_list)

    def fetch_seasons_for_show (self, params):
        """Season for show proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`list`
            Transformed response of the remote call
        """
        show_id = params.get('show_id', [''])[0]
        raw_season_list = self.netflix_session.fetch_seasons_for_show(id=show_id)
        if 'error' in raw_season_list:
            return raw_season_list
        # check if we have sesons, announced shows that are not available yet have none
        if 'seasons' not in raw_season_list.get('value', {}):
              return []
        return self.netflix_session.parse_seasons(id=show_id, response_data=raw_season_list)

    def rate_video (self, params):
        """Video rating proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        video_id = params.get('video_id', [''])[0]
        rating = params.get('rating', [''])[0]
        return self.netflix_session.rate_video(video_id=video_id, rating=rating)

    def remove_from_list (self, params):
        """Remove from my list proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        video_id = params.get('video_id', [''])[0]
        return self.netflix_session.remove_from_list(video_id=video_id)

    def add_to_list (self, params):
        """Add to my list proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        video_id = params.get('video_id', [''])[0]
        return self.netflix_session.add_to_list(video_id=video_id)

    def fetch_metadata (self, params):
        """Metadata proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        video_id = params.get('video_id', [''])[0]
        return self.netflix_session.fetch_metadata(id=video_id)

    def switch_profile (self, params):
        """Switch profile proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        profile_id = params.get('profile_id', [''])[0]
        self.lolomo = None
        return self.netflix_session.switch_profile(profile_id=profile_id, account=self.credentials)

    def get_user_data (self, params):
        """User data getter function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`str`
            Exracted User Data
        """
        return self.netflix_session.user_data

    def search (self, params):
        """Search proxy function

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`list`
            Transformed response of the remote call
        """
        term = params.get('term', [''])[0]
        has_search_results = False
        raw_search_results = self.netflix_session.fetch_search_results(search_str=term)
        # check for any errors
        if 'error' in raw_search_results:
            return raw_search_results

        # determine if we found something
        if 'search' in raw_search_results['value']:
            for key in raw_search_results['value']['search'].keys():
                if self.netflix_session._is_size_key(key=key) == False:
                    has_search_results = raw_search_results['value']['search'][key]['titles']['length'] > 0
                    if has_search_results == False:
                        if raw_search_results['value']['search'][key].get('suggestions', False) != False:
                            for entry in raw_search_results['value']['search'][key]['suggestions']:
                                if self.netflix_session._is_size_key(key=entry) == False:
                                    if raw_search_results['value']['search'][key]['suggestions'][entry]['relatedvideos']['length'] > 0:
                                        has_search_results = True

        # display that we haven't found a thing
        if has_search_results == False:
            return []

        # list the search results
        search_results = self.netflix_session.parse_search_results(response_data=raw_search_results)
        # add more menaingful data to the search results
        raw_search_contents = self.netflix_session.fetch_video_list_information(video_ids=search_results.keys())
        # check for any errors
        if 'error' in raw_search_contents:
            return raw_search_contents
        return self.netflix_session.parse_video_list(response_data=raw_search_contents)

    def _network_availble(self):
        """Check if the network is available
        Returns
        -------
        bool
            Network can be accessed
        """
        try:
            urlopen('http://216.58.192.142', timeout=1)
            return True
        except URLError as err:
            return False
