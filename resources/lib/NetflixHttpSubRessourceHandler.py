class NetflixHttpSubRessourceHandler:

    def __init__ (self, kodi_helper, netflix_session):
        self.kodi_helper = kodi_helper
        self.netflix_session = netflix_session
        credentials = self.kodi_helper.get_credentials()

        if self.netflix_session.is_logged_in(account=credentials):
            self.netflix_session.refresh_session_data(account=credentials)
        else:
            self.netflix_session.login(account=credentials)
        self.profiles = self.netflix_session.profiles

    def is_logged_in (self, params):
        credentials = self.kodi_helper.get_credentials()
        return self.netflix_session.is_logged_in(account=credentials)

    def logout (self, params):
        return self.netflix_session.logout()

    def list_profiles (self, params):
        return self.profiles

    def get_esn (self, params):
        return self.netflix_session.esn

    def fetch_video_list_ids (self, params):
        video_list_ids_raw = self.netflix_session.fetch_video_list_ids()
        if 'error' in video_list_ids_raw:
            return video_list_ids_raw
        return self.netflix_session.parse_video_list_ids(response_data=video_list_ids_raw)

    def fetch_video_list (self, params):
        list_id = params.get('list_id', [''])[0]
        raw_video_list = self.netflix_session.fetch_video_list(list_id=list_id)
        if 'error' in raw_video_list:
            return raw_video_list
        # parse the video list ids
        if 'videos' in raw_video_list.get('value', {}).keys():
            return self.netflix_session.parse_video_list(response_data=raw_video_list)
        return []

    def fetch_episodes_by_season (self, params):
        raw_episode_list = self.netflix_session.fetch_episodes_by_season(season_id=params.get('season_id')[0])
        if 'error' in raw_episode_list:
            return raw_episode_list
        return self.netflix_session.parse_episodes_by_season(response_data=raw_episode_list)

    def fetch_seasons_for_show (self, params):
        show_id = params.get('show_id', [''])[0]
        raw_season_list = self.netflix_session.fetch_seasons_for_show(id=show_id)
        if 'error' in raw_season_list:
            return raw_season_list
        # check if we have sesons, announced shows that are not available yet have none
        if 'seasons' not in raw_season_list.get('value', {}):
              return []
        return self.netflix_session.parse_seasons(id=show_id, response_data=raw_season_list)

    def rate_video (self, params):
        video_id = params.get('video_id', [''])[0]
        rating = params.get('rating', [''])[0]
        return self.netflix_session.rate_video(video_id=video_id, rating=rating)

    def remove_from_list (self, params):
        video_id = params.get('video_id', [''])[0]
        return self.netflix_session.remove_from_list(video_id=video_id)

    def add_to_list (self, params):
        video_id = params.get('video_id', [''])[0]
        return self.netflix_session.add_to_list(video_id=video_id)

    def fetch_metadata (self, params):
        video_id = params.get('video_id', [''])[0]
        return self.netflix_session.fetch_metadata(id=video_id)

    def switch_profile (self, params):
        credentials = self.kodi_helper.get_credentials()
        profile_id = params.get('profile_id', [''])[0]
        return self.netflix_session.switch_profile(profile_id=profile_id, account=credentials)

    def get_user_data (self, params):
        return self.netflix_session.user_data

    def search (self, params):
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
