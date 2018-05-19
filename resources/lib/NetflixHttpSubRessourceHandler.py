# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: NetflixHttpSubRessourceHandler
# Created on: 07.03.2017


class NetflixHttpSubRessourceHandler(object):
    """
    Represents the callable internal server routes &
    translates/executes them to requests for Netflix
    """

    def __init__(self, nx_common, netflix_session):
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
        self.nx_common = nx_common
        self.netflix_session = netflix_session
        self.credentials = self.nx_common.get_credentials()
        self.profiles = []
        self.video_list_cache = {}
        self.prefetch_login()

    def prefetch_login(self):
        """Check if we have stored credentials.
        If so, do the login before the user requests it
        If that is done, we cache the profiles
        """
        self.profiles = []
        email = self.credentials.get('email', '')
        password = self.credentials.get('password', '')
        if email != '' and password != '':
            if self.netflix_session.is_logged_in(account=self.credentials):
                refresh_session = self.netflix_session.refresh_session_data(
                    account=self.credentials)
                if refresh_session:
                    self.profiles = self.netflix_session.profiles
            else:
                if self.netflix_session.login(account=self.credentials):
                    self.profiles = self.netflix_session.profiles

    def is_logged_in(self, params):
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
        email = self.credentials.get('email', '')
        password = self.credentials.get('password', '')
        if email == '' and password == '':
            return False
        return self.netflix_session.is_logged_in(account=self.credentials)

    def logout(self, params):
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

        return self.netflix_session.logout()

    def login(self, params):
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

    def list_profiles(self, params):
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

    def get_esn(self, params):
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

    def fetch_video_list_ids(self, params):
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
        guid = self.netflix_session.user_data.get('guid')
        cached_list = self.video_list_cache.get(guid, None)
        if cached_list is not None:
            self.nx_common.log(msg='Serving cached list for user: ' + guid)
            return cached_list
        video_list_ids_raw = self.netflix_session.fetch_video_list_ids()

        if 'error' in video_list_ids_raw:
            return video_list_ids_raw
        video_list = self.netflix_session.parse_video_list_ids(
            response_data=video_list_ids_raw)
        return video_list

    def fetch_video_list(self, params):
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
        start = int(params.get('list_from', [0])[0])
        end = int(params.get('list_to', [26])[0])
        raw_video_list = self.netflix_session.fetch_video_list(
            list_id=list_id,
            list_from=start,
            list_to=end)
        if 'error' in raw_video_list:
            return raw_video_list
        # parse the video list ids
        if 'videos' in raw_video_list.get('value', {}).keys():
            video_list = self.netflix_session.parse_video_list(
                response_data=raw_video_list)
            return video_list
        return []

    def fetch_episodes_by_season(self, params):
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
        raw_episode_list = self.netflix_session.fetch_episodes_by_season(
            season_id=params.get('season_id')[0])
        if 'error' in raw_episode_list:
            return raw_episode_list
        episodes = self.netflix_session.parse_episodes_by_season(
            response_data=raw_episode_list)
        return episodes

    def fetch_seasons_for_show(self, params):
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
        raw_season_list = self.netflix_session.fetch_seasons_for_show(
            id=show_id)
        if 'error' in raw_season_list:
            return raw_season_list
        # check if we have sesons,
        # announced shows that are not available yet have none
        if 'seasons' not in raw_season_list.get('value', {}):
            return []
        seasons = self.netflix_session.parse_seasons(
            id=show_id,
            response_data=raw_season_list)
        return seasons

    def rate_video(self, params):
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
        rate = self.netflix_session.rate_video(
            video_id=video_id,
            rating=rating)
        return rate

    def remove_from_list(self, params):
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

    def add_to_list(self, params):
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

    def fetch_metadata(self, params):
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

    def send_adult_pin(self, params):
        """Checks the adult pin

        Parameters
        ----------
        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
        :obj:`Requests.Response`
            Response of the remote call
        """
        pin = params.get('pin', [''])[0]
        return self.netflix_session.send_adult_pin(pin=pin)

    def switch_profile(self, params):
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
        switch_profile = self.netflix_session.switch_profile(
            profile_id=profile_id,
            account=self.credentials)
        return switch_profile

    def get_user_data(self, params):
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

    def search(self, params):
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
        raw_search_results = self.netflix_session.fetch_search_results(
            search_str=term)
        # determine if we found something
        videos = raw_search_results.get('value', {}).get('videos', {})
        result_size = len(videos.keys())
        # check for any errors
        if 'error' in raw_search_results or result_size == 0:
            return []
        # list the search results
        search_results = self.netflix_session.parse_video_list(
            response_data=raw_search_results,
            term=term)
        return search_results
