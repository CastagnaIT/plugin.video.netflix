# pylint: skip-file
# -*- coding: utf-8 -*-
# Author: asciidisco
# Module: default
# Created on: 13.01.2017
# License: MIT https://goo.gl/5bMj3H

"""Netflix API management"""

import os
import sys
import json
from time import time
from urllib import quote, unquote
from re import compile as recompile, DOTALL
from base64 import urlsafe_b64encode
from requests import session, cookies
from utils import noop, get_user_agent
from collections import OrderedDict
try:
    import cPickle as pickle
except:
    import pickle

FETCH_VIDEO_REQUEST_COUNT = 26

ART_FANART_SIZE = '1080'
# Lower quality for episodes than 1080, because it provides more variance
# (1080 is usually the same as interestingMoment for episodes)
ART_FANART_SIZE_EPISODE = '720'
ART_MOMENT_SIZE_SMALL = '_665x375'
ART_MOMENT_SIZE_LARGE = '_1920x1080'
ART_BOX_SIZE_POSTER = '_342x684'
ART_BOX_SIZE_SMALL = '_665x375'
ART_BOX_SIZE_LARGE = '_1920x1080'
ART_LOGO_SIZE = '_550x124'


class NetflixSession(object):
    """Helps with login/session management of Netflix users & API handling"""

    base_url = 'https://www.netflix.com'
    """str: Secure Netflix url"""

    urls = {
        'login': '/login',
        'browse': '/browse',
        'video_list_ids': '/preflight',
        'shakti': '/pathEvaluator',
        'profiles':  '/profiles/manage',
        'switch_profiles': '/profiles/switch',
        'adult_pin': '/pin/service',
        'metadata': '/metadata',
        'set_video_rating': '/setVideoRating',
        'update_my_list': '/playlistop',
        'kids': '/Kids'
    }
    """:obj:`dict` of :obj:`str`
    List of all static endpoints for HTML/JSON POST/GET requests"""

    video_list_keys = ['user', 'genres', 'recommendations']
    """:obj:`list` of :obj:`str`
    Divide the users video lists into
    3 different categories (for easier digestion)"""

    profiles = {}
    """:obj:`dict`
        Dict of user profiles, user id is the key:

        "72ERT45...": {
            "profileName": "username",
            "avatar": "http://..../avatar.png",
            "id": "72ERT45...",
            "isAccountOwner": False,
            "isActive": True,
            "isFirstUse": False
        }
    """

    user_data = {}
    """:obj:`dict`
        dict of user data (used for authentication):

        {
            "guid": "72ERT45...",
            "authURL": "145637....",
            "gpsModel": "harris"
        }
    """

    api_data = {}
    """:obj:`dict`
        dict of api data (used to build up the api urls):

        {
            "API_BASE_URL": "/shakti",
            "API_ROOT": "https://www.netflix.com/api",
            "BUILD_IDENTIFIER": "113b89c9", "
            ICHNAEA_ROOT": "/ichnaea"
        }
    """

    esn = ''
    """str: ESN - something like: NFCDCH-MC-D7D6F54LOPY8J416T72MQXX3RD20ME"""

    page_items = [
        'models/userInfo/data/authURL',
        'models/serverDefs/data/BUILD_IDENTIFIER',
        'models/serverDefs/data/ICHNAEA_ROOT',
        'models/serverDefs/data/API_ROOT',
        'models/serverDefs/data/API_BASE_URL',
        'models/esnGeneratorModel/data/esn',
        'gpsModel',
        'models/userInfo/data/countryOfSignup',
        'models/userInfo/data/membershipStatus',
        'models/memberContext/data/geo/preferredLocale'
    ]

    def __init__(self, cookie_path, data_path, verify_ssl, nx_common):
        """Stores the cookie path for later use & instanciates a requests
           session with a proper user agent & stored cookies/data if available

        Parameters
        ----------
        cookie_path : :obj:`str`
            Cookie location

        data_path : :obj:`str`
            User data cache location

        log_fn : :obj:`fn`
             optional log function
        """
        self.cookie_path = cookie_path
        self.data_path = data_path
        self.verify_ssl = verify_ssl
        self.nx_common = nx_common
        self.parsed_cookies = {}
        self.parsed_user_data = {}
        self._init_session()

    def extract_json(self, content, name):
        # Extract json from netflix content page
        json_array = recompile(r"netflix\.%s\s*=\s*(.*?);\s*</script>" % name, DOTALL).findall(content)
        if not json_array:
            return {}  # Return an empty dict if json not found !
        json_str = json_array[0]
        json_str = json_str.replace('\"', '\\"')  # Hook for escape double-quotes
        json_str = json_str.replace('\\s', '\\\\s')  # Hook for escape \s in json regex
        json_str = json_str.decode('unicode_escape')  # finally decoding...
        return json.loads(json_str, encoding='utf-8', strict=False)

    def extract_inline_netflix_page_data(self, content='', items=None):
        """Extract the essential data from the page contents
        The contents of the parsable tags looks something like this:
            <script>
            window.netflix = window.netflix || {} ;
            netflix.notification = {
                "constants":{"sessionLength":30,"ownerToken":"ZDD...};
            </script>
        :return: List
        List of all the serialized data pulled out of the pages <script/> tags
        """
        # Uncomment the two lines below for saving content to disk (if ask you for debug)
        # DO NOT PASTE THE CONTENT OF THIS FILE PUBLICALLY ON THE INTERNET, IT MAY CONTAIN SENSITIVE INFORMATION
        # USE IT ONLY FOR DEBUGGING
        # with open(self.data_path + 'raw_content', "wb") as f:
        #     f.write(content)
        self.nx_common.log(msg='Parsing inline data...')
        items = self.page_items if items is None else items
        user_data = {'gpsModel': 'harris'}
        react_context = self.extract_json(content, 'reactContext')
        # iterate over all wanted item keys & try to fetch them
        for item in items:
            keys = item.split("/")
            val = None
            for key in keys:
                val = val.get(key, None) if val else react_context.get(key, None)
                if not val:
                    break
            if val:
                user_data.update({key: val})
        # fetch profiles & avatars
        profiles = self.get_profiles(content=content)
        # get guid of active user
        for guid in profiles:
            if profiles[guid].get('isActive', False) is True:
                user_data['guid'] = guid

        # verify the data based on the authURL
        is_valid_user_data = self._verfify_auth_and_profiles_data(
            data=user_data,
            profiles=profiles)
        if is_valid_user_data is not False:
            self.nx_common.log(msg='Parsing inline data parsing successfull')
            return (user_data, profiles)
        self.nx_common.log(msg='Parsing inline data failed')
        return (user_data, profiles)

    def get_profiles(self, content):
        """ADD ME"""
        profiles = {}
        falkor_cache = self.extract_json(content, 'falcorCache')
        _profiles = falkor_cache.get('profiles', {})

        for guid in _profiles:
            if not isinstance(_profiles[guid], dict):
                continue
            _profile = _profiles[guid]['summary']
            if 'value' in _profile:
                _profile = _profile['value']
            _avatar_path = _profiles[guid]['avatar']
            if 'value' in _avatar_path:
                _avatar_path = _avatar_path['value']
            _avatar_path.extend([u'images', u'byWidth', u'320', u'value'])
            _profile['avatar'] = self.__recursive_dict(_avatar_path, falkor_cache)
            profiles.update({guid: _profile})

        return profiles

    @staticmethod
    def __recursive_dict(search, dict, index=0):
        if (index + 1 == len(search)):
            return dict[search[index]]
        return NetflixSession.__recursive_dict(search, dict[search[index]], index + 1)

    def is_logged_in(self, account):
        """
        Determines if a user is already logged in (with a valid cookie)

        Parameters
        ----------
        account : :obj:`dict` of :obj:`str`
            Dict containing an email, country & a password property

        Returns
        -------
        bool
            User is already logged in (e.g. Cookie is valid) or not
        """
        # load cookies
        account_hash = self._generate_account_hash(account=account)
        cookies = self._load_cookies(
            filename=self.cookie_path + '_' + account_hash)
        if cookies is False:
            return False

        # find the earliest expiration date in the cookies
        expires = 99999999999999999999
        cur_stamp = int(time())
        for domains in cookies[0]:
            for domain in cookies[0][domains].keys():
                for cookie_key in cookies[0][domains][domain]:
                    if cookies[0][domains][domain][cookie_key].expires is not None:
                        exp = int(cookies[0][domains][domain][cookie_key].expires)
                        if expires > exp:
                            expires = exp
        if expires > cur_stamp:
            self.nx_common.log(
                msg='Cookie expires: ' + str(expires) + ' / ' + str(cur_stamp))
            return True

        # load the profiles page (to verify the user)
        response = self._session_get(component='profiles')
        if response:
            # parse out the needed inline information
            user_data, profiles = self.extract_inline_netflix_page_data(
                content=response.content)
            self.profiles = profiles
            # if we have profiles, cookie is still valid
            if self.profiles:
                return True
        return False

    def logout(self, mslResetCmd=None):
        """
        Delete all cookies and session data

        Parameters
        ----------
        account : :obj:`dict` of :obj:`str`
            Dict containing an email, country & a password property

        """
        self._delete_cookies(path=self.cookie_path)
        self._delete_data(path=self.data_path)

        if mslResetCmd:
            response = session().get(url=mslResetCmd)
            self.nx_common.log(msg='MSL reset return code:' + response)

    def login(self, account):
        """
        Try to log in a user with its credentials
        Stores the cookies & session data if the action is successfull
        Parameters
        ----------
        account : :obj:`dict` of :obj:`str`
            Dict containing an email, country & a password property
        Returns
        -------
        bool
            User could be logged in or not
        """
        page = self._session_get(component='profiles')
        user_data, profiles = self.extract_inline_netflix_page_data(
            content=page.content)
        login_payload = {
            'userLoginId': account.get('email'),
            'email': account.get('email'),
            'password': account.get('password'),
            'rememberMe': 'true',
            'flow': 'websiteSignUp',
            'mode': 'login',
            'action': 'loginAction',
            'withFields': 'rememberMe,nextPage,userLoginId,password,email',
            'authURL': user_data.get('authURL'),
            'nextPage': '',
            'showPassword': ''
        }

        # perform the login
        login_response = self._session_post(
            component='login',
            data=login_payload)
        user_data = self._parse_page_contents(content=login_response.content)
        account_hash = self._generate_account_hash(account=account)
        # we know that the login was successfull if we find ???
        if user_data.get('membershipStatus') == 'CURRENT_MEMBER':
            # store cookies for later requests
            self._save_cookies(filename=self.cookie_path + '_' + account_hash)
            self._save_data(filename=self.data_path + '_' + account_hash)
            return True
        return False

    def switch_profile(self, profile_id, account):
        """
        Switch the user profile based on a given profile id

        Note: All available profiles & their ids can be found in
        the ´profiles´ property after a successfull login

        Parameters
        ----------
        profile_id : :obj:`str`
            User profile id

        account : :obj:`dict` of :obj:`str`
            Dict containing an email, country & a password property

        Returns
        -------
        bool
            User could be switched or not
        """
        payload = {
            'switchProfileGuid': profile_id,
            '_': int(time()),
            'authURL': self.user_data['authURL']
        }

        response = self._session_get(
            component='switch_profiles',
            type='api',
            params=payload)
        if response is None or response.status_code != 200:
            return False

        account_hash = self._generate_account_hash(account=account)
        self.user_data['guid'] = profile_id
        return self._save_data(filename=self.data_path + '_' + account_hash)

    def send_adult_pin(self, pin):
        """
        Send the adult pin to Netflix in case an adult rated video requests it

        Parameters
        ----------
        pin : :obj:`str`
            The users adult pin

        Returns
        -------
        bool
            Pin was accepted or not
        or
        :obj:`dict` of :obj:`str`
            Api call error
        """
        payload = {
            'pin': pin,
            'authURL': self.user_data.get('authURL', '')
        }
        response = self._session_post(
            component='adult_pin',
            type='api',
            data=payload)
        pin_response = self._process_response(
            response=response,
            component=self._get_api_url_for(component='adult_pin'))
        if 'error' in pin_response.keys():
            self.nx_common.log(msg='Pin error')
            self.nx_common.log(msg=str(pin_response))
            return False
        return pin_response.get('success', False)

    def add_to_list(self, video_id):
        """Adds a video to "my list" on Netflix

        Parameters
        ----------
        video_id : :obj:`str`
            ID of th show/video/movie to be added

        Returns
        -------
        bool
            Adding was successfull
        """
        return self._update_my_list(video_id=video_id, operation='add')

    def remove_from_list(self, video_id):
        """Removes a video from "my list" on Netflix

        Parameters
        ----------
        video_id : :obj:`str`
            ID of th show/video/movie to be removed

        Returns
        -------
        bool
            Removing was successfull
        """
        return self._update_my_list(video_id=video_id, operation='remove')

    def rate_video(self, video_id, rating):
        """Rate a video on Netflix

        Parameters
        ----------
        video_id : :obj:`str`
            ID of th show/video/movie to be rated

        rating : :obj:`int`
            Rating, must be between 0 & 10

        Returns
        -------
        bool
            Rating successfull or not
        """

        # dirty rating validation
        rating = int(rating)
        if rating > 10 or rating < 0:
            return False

        # In opposition to Kodi, Netflix uses a rating from 0 to in 0.5 steps
        if rating != 0:
            rating = rating / 2

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/javascript, */*',
        }

        params = {
            'titleid': video_id,
            'rating': rating
        }

        payload = json.dumps({
            'authURL': self.user_data['authURL']
        })

        response = self._session_post(
            component='set_video_rating',
            type='api',
            params=params,
            headers=headers,
            data=payload)

        if response and response.status_code == 200:
            return True

        return False

    def parse_video_list_ids(self, response_data):
        """Parse the list of video ids e.g. rip out the parts we need

        Parameters
        ----------
        response_data : :obj:`dict` of :obj:`str`
            Parsed response JSON from the ´fetch_video_list_ids´ call

        Returns
        -------
        :obj:`dict` of :obj:`dict`
            Video list ids in the format:

            {
                "genres": {
                    "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568367": {
                        "displayName": "US-Serien",
                        "id": "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568367",
                        "index": 3,
                        "name": "genre",
                        "size": 38
                    },
                    "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568368": {
                        "displayName": ...
                    },
                },
                "user": {
                    "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568364": {
                        "displayName": "Meine Liste",
                        "id": "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568364",
                        "index": 0,
                        "name": "queue",
                        "size": 2
                    },
                    "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568365": {
                        "displayName": ...
                    },
                },
                "recommendations": {
                    "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568382": {
                        "displayName": "Passend zu Family Guy",
                        "id": "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568382",
                        "index": 18,
                        "name": "similars",
                        "size": 33
                    },
                    "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568397": {
                        "displayName": ...
                    }
                }
            }
        """
        # prepare the return dictionary
        video_list_ids = {}
        for key in self.video_list_keys:
            video_list_ids[key] = {}

        # check if the list items are hidden behind a `value` sub key
        # this is the case when we fetch the lists via POST,
        # not via a GET preflight request
        if 'value' in response_data.keys():
            response_data = response_data.get('value')

        # subcatogorize the lists by their context
        video_lists = response_data.get('lists', {})
        for video_list_id in video_lists.keys():
            video_list = video_lists[video_list_id]
            if video_list.get('context', False) is not False:
                ctx = video_list.get('context')
                video_list_entry = self.parse_video_list_ids_entry(
                    id=video_list_id,
                    entry=video_list)
                if ctx == 'genre':
                    video_list_ids['genres'].update(video_list_entry)
                elif ctx == 'similars' or ctx == 'becauseYouAdded':
                    video_list_ids['recommendations'].update(video_list_entry)
                else:
                    video_list_ids['user'].update(video_list_entry)
        return video_list_ids

    def parse_video_list_ids_entry(self, id, entry):
        """Parse a video id entry e.g. rip out the parts we need

        Parameters
        ----------
        response_data : :obj:`dict` of :obj:`str`
            Dictionary entry from the ´fetch_video_list_ids´ call

        Returns
        -------
        id : :obj:`str`
            Unique id of the video list

        entry : :obj:`dict` of :obj:`str`
            Video list entry in the format:

            "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568382": {
                "displayName": "Passend zu Family Guy",
                "id": "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568382",
                "index": 18,
                "name": "similars",
                "size": 33
            }
        """
        return {
            id: {
                'id': id,
                'index': entry['index'],
                'name': entry['context'],
                'displayName': entry['displayName'],
                'size': entry['length']
            }
        }

    def parse_video_list(self, response_data, term=None):
        """Parse a list of videos

        Parameters
        ----------
        response_data : :obj:`dict` of :obj:`str`
            Parsed response JSON from the `fetch_video_list` call

        Returns
        -------
        :obj:`dict` of :obj:`dict`
            Video list in the format:

            {
                "372203": {
                    "artwork": null,
                    "boxarts": {
                      "big": "https://art-s.nflximg.net/5e7d3/b....jpg",
                      "small": "https://art-s.nflximg.net/57543/a....jpg"
                    },
                    "cast": [
                      "Christine Elise",
                      "Brad Dourif",
                      "Grace Zabriskie",
                      "Jenny Agutter",
                      "John Lafia",
                      "Gerrit Graham",
                      "Peter Haskell",
                      "Alex Vincent",
                      "Beth Grant"
                    ],
                    "creators": [],
                    "directors": [],
                    "episode_count": null,
                    "genres": [
                      "Horrorfilme"
                    ],
                    "id": "372203",
                    "in_my_list": true,
                    "interesting_moment": "https://art-s.nflximg.net/0....jpg",
                    "list_id": "9588df32-f957-40e4-9055-1f6f33b60103_46891306",
                    "maturity": {
                      "board": "FSK",
                      "description": "Nur f\u00fcr Erwachsene geeignet.",
                      "level": 1000,
                      "value": "18"
                    },
                    "quality": "540",
                    "rating": 3.1707757,
                    "regular_synopsis": "Ein Spielzeughersteller e....",
                    "runtime": 5028,
                    "seasons_count": null,
                    "seasons_label": null,
                    "synopsis": "Die allseits beliebte, vo....",
                    "tags": [
                      "Brutal",
                      "Spannend"
                    ],
                    "title": "Chucky 2 \u2013 Die M\u00f6rderpuppe ist...",
                    "type": "movie",
                    "watched": false,
                    "year": 1990
                },
                "80011356": {
                    "artwork": null,
                    "boxarts": {
                      "big": "https://art-s.nflximg.net/7c10d/5dc....jpg",
                      "small": "https://art-s.nflximg.net/5bc0e/f3be3....jpg"
                    },
                    "cast": [
                      "Bjarne M\u00e4del"
                    ],
                    "creators": [],
                    "directors": [
                      "Arne Feldhusen"
                    ],
                    "episode_count": 24,
                    "genres": [
                      "Deutsche Serien",
                      "Serien",
                      "Comedyserien"
                    ],
                    "id": "80011356",
                    "in_my_list": true,
                    "interesting_moment": "https://art-s.nflximg.net/01...jpg",
                    "list_id": "9588df32-f957-40e4-9055-1f6f33b60103_46891306",
                    "maturity": {
                      "board": "FSF",
                      "description": "Geeignet ab 12 Jahren.",
                      "level": 80,
                      "value": "12"
                    },
                    "quality": "720",
                    "rating": 4.4394655,
                    "regular_synopsis": "Comedy-Serie \u00fcber...",
                    "runtime": null,
                    "seasons_count": 5,
                    "seasons_label": "5 Staffeln",
                    "synopsis": "In den meisten Krimiserien werde...",
                    "tags": [
                      "Zynisch"
                    ],
                    "title": "Der Tatortreiniger",
                    "type": "show",
                    "watched": false,
                    "year": 2015
                },
            }
        """
        video_ids = []
        raw_video_list = response_data.get('value', {})
        # search results have sorting given in references
        if term and 'search' in raw_video_list:
           try:
               reference = raw_video_list.get('search').get('byTerm').get('|'+term).get('titles').get('48')[2]
               references = raw_video_list.get('search').get('byReference').get(reference)
               for reference_id in range (0, 48):
                   video_ids.append(references.get(str(reference_id)).get('reference')[1])
           except:
               return {}
        else:
            for video_id in raw_video_list.get('videos', {}):
                if self._is_size_key(key=video_id) is False:
                    video_ids.append(video_id);

        video_list = OrderedDict()
        netflix_list_id = self.parse_netflix_list_id(video_list=raw_video_list)
        for video_id in video_ids:
            video_list_entry = self.parse_video_list_entry(
                id=video_id,
                list_id=netflix_list_id,
                video=raw_video_list.get('videos', {}).get(video_id),
                persons=raw_video_list.get('person'),
                genres=raw_video_list.get('genres'))
            video_list.update(video_list_entry)

        return video_list

    def parse_video_list_entry(self, id, list_id, video, persons, genres):
        """Parse a video list entry e.g. rip out the parts we need

        Parameters
        ----------
        id : :obj:`str`
            Unique id of the video

        list_id : :obj:`str`
            Unique id of the containing list

        video : :obj:`dict` of :obj:`str`
            Video entry from the ´fetch_video_list´ call

        persons : :obj:`dict` of :obj:`dict` of :obj:`str`
            List of persons with reference ids

        persons : :obj:`dict` of :obj:`dict` of :obj:`str`
            List of genres with reference ids

        Returns
        -------
        entry : :obj:`dict` of :obj:`dict` of :obj:`str`
            Video list entry in the format:

           {
              "372203": {
                "artwork": null,
                "boxarts": {
                  "big": "https://art-s.nflximg.net/5e7d3/b3b...b55e7d3.jpg",
                  "small": "https://art-s.nflximg.net/57543/a039...957543.jpg"
                },
                "cast": [
                  "Christine Elise",
                  "Brad Dourif",
                  "Grace Zabriskie",
                  "Jenny Agutter",
                  "John Lafia",
                  "Gerrit Graham",
                  "Peter Haskell",
                  "Alex Vincent",
                  "Beth Grant"
                ],
                "creators": [],
                "directors": [],
                "episode_count": null,
                "genres": [
                  "Horrorfilme"
                ],
                "id": "372203",
                "in_my_list": true,
                "interesting_moment": "https://art-s.nflximg.net/095...4.jpg",
                "list_id": "9588df32-f957-40e4-9055-1f6f33b60103_46891306",
                "maturity": {
                  "board": "FSK",
                  "description": "Nur f\u00fcr Erwachsene geeignet.",
                  "level": 1000,
                  "value": "18"
                },
                "quality": "540",
                "rating": 3.1707757,
                "regular_synopsis": "Ein Spielzeughersteller erweck...",
                "runtime": 5028,
                "seasons_count": null,
                "seasons_label": null,
                "synopsis": "Die allseits beliebte, von D\u00e4mone...",
                "tags": [
                  "Brutal",
                  "Spannend"
                ],
                "title": "Chucky 2 \u2013 Die M\u00f6rderpuppe ist wieder da",
                "type": "movie",
                "watched": false,
                "year": 1990
              }
            }
        """
        season_info = self.parse_season_information_for_video(video=video)

        # determine rating
        rating = 0
        user_rating = video.get('userRating', {})
        if user_rating.get('average', None) is not None:
            rating = user_rating.get('average', 0)
        else:
            rating = user_rating.get('predicted', 0)

        # determine maturity data
        maturity_rating = video.get('maturity', {}).get('rating', {})
        maturity = {
            'board': maturity_rating.get('board', None),
            'value': maturity_rating.get('value', None),
            'description': maturity_rating.get('maturityDescription', None),
            'level': maturity_rating.get('maturityLevel', None),
        }

        # determine artwork
        boxarts = video.get('boxarts', {})
        bx_small = boxarts.get(ART_BOX_SIZE_SMALL, {}).get('jpg', {}).get('url')
        bx_big = boxarts.get(ART_BOX_SIZE_LARGE, {}).get('jpg', {}).get('url')
        bx_poster = boxarts.get(ART_BOX_SIZE_POSTER, {}).get('jpg', {}).get('url')
        moment = video.get('interestingMoment', {}).get(ART_MOMENT_SIZE_LARGE, {}).get('jpg', {}).get('url')
        artwork = next(iter(video.get('BGImages', {}).get(ART_FANART_SIZE, {}).get('jpg', [{}])), {}).get('url')
        logo = video.get('bb2OGLogo', {}).get(ART_LOGO_SIZE, {}).get('png', {}).get('url')

        return {
            id: {
                'id': id,
                'list_id': list_id,
                'title': video.get('title'),
                'synopsis': video.get('synopsis'),
                'regular_synopsis': video.get('regularSynopsis'),
                'type': video.get('summary', {}).get('type'),
                'rating': rating,
                'episode_count': season_info.get('episode_count'),
                'seasons_label': season_info.get('seasons_label'),
                'seasons_count': season_info.get('seasons_count'),
                'in_my_list': video.get('queue', {}).get('inQueue'),
                'year': video.get('releaseYear'),
                'runtime': self.parse_runtime_for_video(video=video),
                'watched': video.get('watched', None),
                'tags': self.parse_tags_for_video(video=video),
                'genres': self.parse_genres_for_video(
                    video=video,
                    genres=genres),
                'quality': self.parse_quality_for_video(video=video),
                'cast': self.parse_cast_for_video(
                    video=video,
                    persons=persons),
                'directors': self.parse_directors_for_video(
                    video=video,
                    persons=persons),
                'creators': self.parse_creators_for_video(
                    video=video,
                    persons=persons),
                'maturity': maturity,
                'boxarts': {
                    'small': bx_small,
                    'big': bx_big,
                    'poster': bx_poster
                },
                'interesting_moment': moment,
                'artwork': artwork,
                'clearlogo': logo
            }
        }

    def parse_creators_for_video(self, video, persons):
        """Matches ids with person names to generate a list of creators

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        persons : :obj:`dict` of :obj:`str`
            Raw resposne of all persons delivered by the API call

        Returns
        -------
        :obj:`list` of :obj:`str`
            List of creators
        """
        creators = []
        for person_key in dict(persons).keys():
            is_size_key = self._is_size_key(key=person_key)
            if is_size_key is False and person_key != 'summary':
                for creator_key in dict(video.get('creators', {})).keys():
                    is_size_key = self._is_size_key(key=creator_key)
                    if is_size_key is False and creator_key != 'summary':
                        if video['creators'][creator_key][1] == person_key:
                            creators.append(persons[person_key]['name'])
        return creators

    def parse_directors_for_video(self, video, persons):
        """Matches ids with person names to generate a list of directors

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        persons : :obj:`dict` of :obj:`str`
            Raw resposne of all persons delivered by the API call

        Returns
        -------
        :obj:`list` of :obj:`str`
            List of directors
        """
        directors = []
        for person_key in dict(persons).keys():
            is_size_key = self._is_size_key(key=person_key)
            if is_size_key is False and person_key != 'summary':
                for director_key in dict(video.get('directors', {})).keys():
                    is_size_key = self._is_size_key(key=director_key)
                    if is_size_key is False and director_key != 'summary':
                        if video['directors'][director_key][1] == person_key:
                            directors.append(persons[person_key]['name'])
        return directors

    def parse_cast_for_video(self, video, persons):
        """Matches ids with person names to generate a list of cast members

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        persons : :obj:`dict` of :obj:`str`
            Raw resposne of all persons delivered by the API call

        Returns
        -------
        :obj:`list` of :obj:`str`
            List of cast members
        """
        cast = []
        for person_key in dict(persons).keys():
            is_size_key = self._is_size_key(key=person_key)
            if is_size_key is False and person_key != 'summary':
                for cast_key in dict(video['cast']).keys():
                    is_size_key = self._is_size_key(key=cast_key)
                    if is_size_key is False and cast_key != 'summary':
                        if video['cast'][cast_key][1] == person_key:
                            cast.append(persons[person_key]['name'])
        return cast

    def parse_genres_for_video(self, video, genres):
        """Matches ids with genre names to generate a list of genres for a video

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        genres : :obj:`dict` of :obj:`str`
            Raw resposne of all genres delivered by the API call

        Returns
        -------
        :obj:`list` of :obj:`str`
            List of genres
        """
        video_genres = []

        for video_key, video_genre in video.get('genres', {}).iteritems():
            is_size_key = self._is_size_key(key=video_key)
            if is_size_key is False and video_key != 'summary':
                name = genres.get(video_genre[1], {}).get('name')
                if name:
                    video_genres.append(name)
        return video_genres

    def parse_tags_for_video(self, video):
        """
        Parses a nested list of tags, removes the not needed meta information
        & returns a raw string list

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        Returns
        -------
        :obj:`list` of :obj:`str`
            List of tags
        """
        tags = []
        for tag in video.get('tags', {}).keys():
            if self._is_size_key(key=tag) is False and tag != 'summary':
                tags.append(video.get('tags', {}).get(tag, {}).get('name'))
        return tags

    def parse_season_information_for_video(self, video):
        """
        Checks if the fiven video is a show (series) and
        returns season & episode information

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        Returns
        -------
        :obj:`dict` of :obj:`str`
            Episode count / Season Count & Season label if given
        """
        season_info = {
            'episode_count': None,
            'seasons_label': None,
            'seasons_count': None
        }
        if video['summary']['type'] == 'show':
            season_info = {
                'episode_count': video['episodeCount'],
                'seasons_label': video['numSeasonsLabel'],
                'seasons_count': video['seasonCount']
            }
        return season_info

    def parse_quality_for_video(self, video):
        """Transforms Netflix quality information in video resolution info

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        Returns
        -------
        :obj:`str`
            Quality of the video
        """
        quality = '720'
        if video.get('delivery', {}).get('hasHD', None):
            quality = '1080'
        if video.get('delivery', {}).get('hasUltraHD', None):
            quality = '4000'
        return quality

    def parse_runtime_for_video(self, video):
        """Checks if the video is a movie & returns the runtime if given

        Parameters
        ----------
        video : :obj:`dict` of :obj:`str`
            Dictionary entry for one video entry

        Returns
        -------
        :obj:`str`
            Runtime of the video (in seconds)
        """
        runtime = None
        if video.get('summary', {}).get('type') != 'show':
            runtime = video.get('runtime')
        return runtime

    def parse_netflix_list_id(self, video_list):
        """Parse a video list and extract the list id

        Parameters
        ----------
        video_list : :obj:`dict` of :obj:`str`
            Netflix video list

        Returns
        -------
        entry : :obj:`str` or None
            Netflix list id
        """
        netflix_list_id = None
        if 'lists' in video_list.keys():
            for video_id in video_list.get('lists', {}):
                if self._is_size_key(key=video_id) is False:
                    netflix_list_id = video_id
        return netflix_list_id

    def parse_seasons(self, id, response_data):
        """Parse a list of seasons for a given show

        Parameters
        ----------
        id : :obj:`str`
            Season id

        response_data : :obj:`dict` of :obj:`str`
            Parsed response JSON from the `fetch_seasons_for_show` call

        Returns
        -------
        entry : :obj:`dict` of :obj:`dict` of :obj:`str`
        Season information in the format:
            {
                "80113084": {
                    "id": 80113084,
                    "text": "Season 1",
                    "shortName": "St. 1",
                    "boxarts": {
                      "big": "https://art-s.nflximg.net/5e7d3/b3b4....jpg",
                      "small": "https://art-s.nflximg.net/57543/a039....jpg"
                    },
                    "interesting_moment": "https://art-s.nflximg.net/09....jpg"
                },
                "80113085": {
                    "id": 80113085,
                    "text": "Season 2",
                    "shortName": "St. 2",
                    "boxarts": {
                      "big": "https://art-s.nflximg.net/5e7d3/....jpg",
                      "small": "https://art-s.nflximg.net/57543/a03....jpg"
                    },
                    "interesting_moment": "https://art-s.nflximg....4.jpg"
                }
            }
        """
        raw_seasons = response_data['value']
        videos = raw_seasons['videos']

        # get art video key
        video = {}
        for key, video_candidate in videos.iteritems():
            if not self._is_size_key(key):
                video = video_candidate

        # get season index
        sorting = {}
        for idx, season_list_entry in video['seasonList'].iteritems():
            if self._is_size_key(key=idx) is False and idx != 'summary':
                sorting[int(season_list_entry[1])] = int(idx)

        seasons = {}

        for season in raw_seasons['seasons']:
            if self._is_size_key(key=season) is False:
                season_entry = self._parse_season_entry(
                    season=raw_seasons.get('seasons', {}).get(season),
                    video=video,
                    sorting=sorting)
                seasons.update(season_entry)
        return seasons

    def _parse_season_entry(self, season, video, sorting):
        """Parse a season list entry e.g. rip out the parts we need

        Parameters
        ----------
        season : :obj:`dict` of :obj:`str`
            Season entry from the `fetch_seasons_for_show` call

        Returns
        -------
        entry : :obj:`dict` of :obj:`dict` of :obj:`str`
            Season list entry in the format:

            {
                "80113084": {
                    "id": 80113084,
                    "text": "Season 1",
                    "shortName": "St. 1",
                    "boxarts": {
                      "big": "https://art-s.nflximg.net/5e7d3/b3b4....jpg",
                      "small": "https://art-s.nflximg.net/57543/a0398....jpg"
                    },
                    "interesting_moment": "https://art-s.nflximg.net/095...jpg"
                }
            }
        """
        # determine artwork
        boxarts = video.get('boxarts', {})
        bx_small = boxarts.get(ART_BOX_SIZE_SMALL, {}).get('jpg', {}).get('url')
        bx_big = boxarts.get(ART_BOX_SIZE_LARGE, {}).get('jpg', {}).get('url')
        bx_poster = boxarts.get(ART_BOX_SIZE_POSTER, {}).get('jpg', {}).get('url')
        moment = video.get('interestingMoment', {}).get(ART_MOMENT_SIZE_LARGE, {}).get('jpg', {}).get('url')
        artwork = next(iter(video.get('BGImages', {}).get(ART_FANART_SIZE, {}).get('jpg', [{}])), {}).get('url')
        logo = video.get('bb2OGLogo', {}).get(ART_LOGO_SIZE, {}).get('png', {}).get('url')
        return {
            season['summary']['id']: {
                'idx': sorting[season['summary']['id']],
                'id': season['summary']['id'],
                'text': season['summary']['name'],
                'shortName': season['summary']['shortName'],
                'boxarts': {
                    'small': bx_small,
                    'big': bx_big,
                    'poster': bx_poster
                },
                'interesting_moment': moment,
                'artwork': artwork,
                'clearlogo': logo,
                'type': 'season'
            }
        }

    def parse_episodes_by_season(self, response_data):
        """Parse episodes for a given season/episode list

        Parameters
        ----------
        response_data : :obj:`dict` of :obj:`str`
            Parsed response JSON from the `fetch_seasons_for_show` call

        Returns
        -------
        entry : :obj:`dict` of :obj:`dict` of :obj:`str`
        Season information in the format:

        {
          "70251729": {
            "banner": "https://art-s.nflximg.net/63a36/c7fdfe66...jpg",
            "duration": 1387,
            "episode": 1,
            "fanart": "https://art-s.nflximg.net/74e02/e7edcc5cc7d....jpg",
            "genres": [
              "Serien",
              "Comedyserien"
            ],
            "id": 70251729,
            "mediatype": "episode",
            "mpaa": "FSK 16",
            "my_list": false,
            "playcount": 0,
            "plot": "Als die Griffins und andere Einwohner von...",
            "poster": "https://art-s.nflximg.net/72fd6/57088715e8d...jpg",
            "rating": 3.9111512,
            "season": 9,
            "thumb": "https://art-s.nflximg.net/be686/07680670a68d....jpg",
            "title": "Und dann gab es weniger (Teil 1)",
            "year": 2010,
            "bookmark": -1
          },
          "70251730": {
            "banner": "https://art-s.nflximg.net/63a36/c7fdfe6604ef2c...jpg",
            "duration": 1379,
            "episode": 2,
            "fanart": "https://art-s.nflximg.net/c472c/6c10f9578bf2c....jpg",
            "genres": [
              "Serien",
              "Comedyserien"
            ],
            "id": 70251730,
            "mediatype": "episode",
            "mpaa": "FSK 16",
            "my_list": false,
            "playcount": 1,
            "plot": "Wer ist der M\u00f6rder? Nach zahlreichen...",
            "poster": "https://art-s.nflximg.net/72fd6/5708...jpg",
            "rating": 3.9111512,
            "season": 9,
            "thumb": "https://art-s.nflximg.net/15a08/857d5912...jpg",
            "title": "Und dann gab es weniger (Teil 2)",
            "year": 2010,
            "bookmark": 1234
          },
        }
        """
        episodes = {}
        raw_episodes = response_data['value']['videos']
        for episode_id in raw_episodes:
            if self._is_size_key(key=episode_id) is False:
                if (raw_episodes[episode_id]['summary']['type'] == 'episode'):
                    episode_entry = self.parse_episode(
                        episode=raw_episodes[episode_id],
                        genres=response_data.get('value', {}).get('genres'))
                    episodes.update(episode_entry)
        return episodes

    def parse_episode(self, episode, genres=None):
        """Parse episode from an list of episodes by season

        Parameters
        ----------
        episode : :obj:`dict` of :obj:`str`
            Episode entry from the `fetch_episodes_by_season` call

        Returns
        -------
        entry : :obj:`dict` of :obj:`dict` of :obj:`str`
        Episode information in the format:

        {
          "70251729": {
            "banner": "https://art-s.nflximg.net/63a36/c7fdfe...6.jpg",
            "duration": 1387,
            "episode": 1,
            "fanart": "https://art-s.nflximg.net/74e02/e7edcc5cc7....jpg",
            "genres": [
              "Serien",
              "Comedyserien"
            ],
            "id": 70251729,
            "mediatype": "episode",
            "mpaa": "FSK 16",
            "my_list": false,
            "playcount": 0,
            "plot": "Als die Griffins und andere Einwohner von Quahog...",
            "poster": "https://art-s.nflximg.net/72fd6/57088715e8...jpg",
            "rating": 3.9111512,
            "season": 9,
            "thumb": "https://art-s.nflximg.net/be686/07680670a68...jpg",
            "title": "Und dann gab es weniger (Teil 1)",
            "year": 2010,
            "bookmark": 1234
          },
        }
        """
        maturity = episode.get('maturity', {})
        mpaa = str(maturity.get('board', '').encode('utf-8'))
        mpaa += '-'
        mpaa += str(maturity.get('value', '').encode('utf-8'))

        rating = episode.get('userRating', {}).get('predicted', 0)
        rating = episode.get('userRating', {}).get('average', rating)

        # determine artwork
        boxarts = episode.get('boxarts', {})
        bx_small = boxarts.get(ART_BOX_SIZE_SMALL, {}).get('jpg', {}).get('url')
        bx_big = boxarts.get(ART_BOX_SIZE_LARGE, {}).get('jpg', {}).get('url')
        bx_poster = boxarts.get(ART_BOX_SIZE_POSTER, {}).get('jpg', {}).get('url')
        moment = episode.get('interestingMoment', {}).get(ART_MOMENT_SIZE_LARGE, {}).get('jpg', {}).get('url')
        artwork = next(iter(episode.get('BGImages', {}).get(ART_FANART_SIZE_EPISODE, {}).get('jpg', [{}])), {}).get('url')
        logo = episode.get('bb2OGLogo', {}).get(ART_LOGO_SIZE, {}).get('png', {}).get('url')

        return {
            episode['summary']['id']: {
                'id': episode['summary']['id'],
                'episode': episode['summary']['episode'],
                'season': episode['summary']['season'],
                'plot': episode['synopsis'],
                'duration': episode['runtime'],
                'title': episode['title'],
                'year': episode['releaseYear'],
                'genres': self.parse_genres_for_video(
                    video=episode,
                    genres=genres),
                'mpaa': mpaa,
                'maturity': episode['maturity'],
                'playcount': (0, 1)[episode.get('watched')],
                'rating': rating,
                'mediatype': episode.get('summary', {}).get('type', 'movie'),
                'my_list': episode['queue']['inQueue'],
                'bookmark': episode['bookmarkPosition'],
                'boxarts': {
                    'small': bx_small,
                    'big': bx_big,
                    'poster': bx_poster
                },
                'interesting_moment': moment,
                'artwork': artwork,
                'clearlogo': logo,
                'type': 'episode'
            }
        }

    def fetch_video_list_ids(self, list_from=0, list_to=50):
        """
        Fetches the JSON with detailed information based on the
        lists on the landing page (browse page) of Netflix

        Parameters
        ----------
        list_from : :obj:`int`
            Start entry for pagination

        list_to : :obj:`int`
            Last entry for pagination

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        paths = [
            [
                'lolomo',
                {'from': list_from, 'to': list_to},
                ['displayName', 'context', 'id', 'index', 'length']
            ]
        ]

        response = self._path_request(paths=paths)
        return self._process_response(
            response=response,
            component='Video list ids')

    def fetch_search_results(self, search_str, list_from=0, list_to=48):
        """
        Fetches the JSON which contains the results for the given search query

        Parameters
        ----------
        search_str : :obj:`str`
            String to query Netflix search for

        list_from : :obj:`int`
            Start entry for pagination

        list_to : :obj:`int`
            Last entry for pagination

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        # reusable query items
        item_path = ['search', 'byTerm', '|' + search_str]
        item_titles = ['titles', list_to]
        item_pagination = [{'from': list_from, 'to': list_to}]

        paths = [
            item_path + item_titles + item_pagination + ['reference', ['summary', 'releaseYear', 'title', 'synopsis', 'regularSynopsis', 'evidence', 'queue', 'episodeCount', 'info', 'maturity', 'runtime', 'seasonCount', 'releaseYear', 'userRating', 'numSeasonsLabel', 'bookmarkPosition', 'watched', 'delivery', 'seasonList', 'current']],
            item_path + item_titles + item_pagination + ['reference', 'bb2OGLogo', ART_LOGO_SIZE, 'png'],
            item_path + item_titles + item_pagination + ['reference', 'boxarts', ART_BOX_SIZE_SMALL, 'jpg'],
            item_path + item_titles + item_pagination + ['reference', 'boxarts', ART_BOX_SIZE_LARGE, 'jpg'],
            item_path + item_titles + item_pagination + ['reference', 'boxarts', ART_BOX_SIZE_POSTER, 'jpg'],
            item_path + item_titles + item_pagination + ['reference', 'storyarts', '_1632x873', 'jpg'],
            item_path + item_titles + item_pagination + ['reference', 'interestingMoment', ART_MOMENT_SIZE_SMALL, 'jpg'],
            item_path + item_titles + item_pagination + ['reference', 'interestingMoment', ART_MOMENT_SIZE_LARGE, 'jpg'],
            item_path + item_titles + item_pagination + ['reference', 'BGImages', ART_FANART_SIZE, 'jpg'],
            item_path + item_titles + item_pagination + ['reference', 'cast', {'from': 0, 'to': 15}, ['id', 'name']],
            item_path + item_titles + item_pagination + ['reference', 'cast', 'summary'],
            item_path + item_titles + item_pagination + ['reference', 'genres', {'from': 0, 'to': 5}, ['id', 'name']],
            item_path + item_titles + item_pagination + ['reference', 'genres', 'summary'],
            item_path + item_titles + item_pagination + ['reference', 'tags', {'from': 0, 'to': 9}, ['id', 'name']],
            item_path + item_titles + item_pagination + ['reference', 'tags', 'summary'],
            item_path + item_titles + [['referenceId', 'id', 'length', 'name', 'trackIds', 'requestId', 'regularSynopsis', 'evidence']]]

        response = self._path_request(paths=paths)
        return self._process_response(
            response=response,
            component='Search results')

    def fetch_video_list(self, list_id, list_from=0, list_to=None):
        """Fetches the JSON which contains the contents of a given video list

        Parameters
        ----------
        list_id : :obj:`str`
            Unique list id to query Netflix for

        list_from : :obj:`int`
            Start entry for pagination

        list_to : :obj:`int`
            Last entry for pagination

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        if list_to is None:
            list_to = FETCH_VIDEO_REQUEST_COUNT

        paths = [
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", ['summary', 'title', 'synopsis', 'regularSynopsis', 'evidence', 'queue', 'episodeCount', 'info', 'maturity', 'runtime', 'seasonCount', 'releaseYear', 'userRating', 'numSeasonsLabel', 'bookmarkPosition', 'watched', 'delivery']],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'cast', {'from': 0, 'to': 15}, ['id', 'name']],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'cast', 'summary'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'genres', {'from': 0, 'to': 5}, ['id', 'name']],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'genres', 'summary'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'tags', {'from': 0, 'to': 9}, ['id', 'name']],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'tags', 'summary'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", ['creators', 'directors'], {'from': 0, 'to': 49}, ['id', 'name']],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", ['creators', 'directors'], 'summary'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'bb2OGLogo', ART_LOGO_SIZE, 'png'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'boxarts', ART_BOX_SIZE_SMALL, 'jpg'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'boxarts', ART_BOX_SIZE_LARGE, 'jpg'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'boxarts', ART_BOX_SIZE_POSTER, 'jpg'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'storyarts', '_1632x873', 'jpg'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'interestingMoment', ART_MOMENT_SIZE_SMALL, 'jpg'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'interestingMoment', ART_MOMENT_SIZE_LARGE, 'jpg'],
            ['lists', [list_id], {'from': list_from, 'to': list_to}, "reference", 'BGImages', ART_FANART_SIZE, 'jpg']
        ]

        response = self._path_request(paths=paths)
        processed_resp = self._process_response(
            response=response,
            component='Video list')
        return processed_resp

    def fetch_metadata(self, id):
        """
        Fetches the JSON which contains the metadata for a
        given show/movie or season id

        Parameters
        ----------
        id : :obj:`str`
            Show id, movie id or season id

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        payload = {
            'movieid': id,
            'imageformat': 'jpg',
            '_': int(time())
        }
        response = self._session_get(
            component='metadata',
            params=payload,
            type='api')
        return self._process_response(
            response=response,
            component=self._get_api_url_for(component='metadata'))

        """Fetches the JSON which contains the detailed contents of a show

        Parameters
        ----------
        id : :obj:`str`
            Unique show id to query Netflix for

        type : :obj:`str`
            Can be 'movie' or 'show'

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        # check if we have a show or a movie, the request made depends on this
        if type == 'show':
            paths = [
                ['videos', id, ['requestId', 'regularSynopsis', 'evidence']],
                ['videos', id, 'seasonList', 'current', 'summary']
            ]
        else:
            paths = [
                ['videos', id, ['requestId', 'regularSynopsis', 'evidence']]
            ]
        response = self._path_request(paths=paths)
        return self._process_response(
            response=response,
            component='Show information')

    def fetch_seasons_for_show(self, id, list_from=0, list_to=30):
        """Fetches the JSON which contains the seasons of a given show

        Parameters
        ----------
        id : :obj:`str`
            Unique show id to query Netflix for

        list_from : :obj:`int`
            Start entry for pagination

        list_to : :obj:`int`
            Last entry for pagination

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        paths = [
            ['videos', id, 'seasonList', {'from': list_from, 'to': list_to}, 'summary'],
            ['videos', id, 'seasonList', 'summary'],
            ['videos', id, 'boxarts',  ART_BOX_SIZE_SMALL, 'jpg'],
            ['videos', id, 'boxarts', ART_BOX_SIZE_LARGE, 'jpg'],
            ['videos', id, 'boxarts', ART_BOX_SIZE_POSTER, 'jpg'],
            ['videos', id, 'storyarts',  '_1632x873', 'jpg'],
            ['videos', id, 'bb2OGLogo', ART_LOGO_SIZE, 'png'],
            ['videos', id, 'interestingMoment', ART_MOMENT_SIZE_SMALL, 'jpg'],
            ['videos', id, 'interestingMoment', ART_MOMENT_SIZE_LARGE, 'jpg'],
            ['videos', id, 'BGImages', ART_FANART_SIZE, 'jpg']
        ]
        response = self._path_request(paths=paths)
        return self._process_response(response=response, component='Seasons')

    def fetch_episodes_by_season(self, season_id, list_from=-1, list_to=40):
        """Fetches the JSON which contains the episodes of a given season

        TODO: Add more metadata

        Parameters
        ----------
        season_id : :obj:`str`
            Unique season_id id to query Netflix for

        list_from : :obj:`int`
            Start entry for pagination

        list_to : :obj:`int`
            Last entry for pagination

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        paths = [
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, ['summary', 'synopsis', 'title', 'runtime', 'releaseYear', 'queue', 'info', 'maturity', 'userRating', 'bookmarkPosition', 'creditOffset', 'watched', 'delivery']],
            # ['videos', season_id, 'cast', {'from': 0, 'to': 15}, ['id', 'name']],
            # ['videos', season_id, 'cast', 'summary'],
            # ['videos', season_id, 'genres', {'from': 0, 'to': 5}, ['id', 'name']],
            # ['videos', season_id, 'genres', 'summary'],
            # ['videos', season_id, 'tags', {'from': 0, 'to': 9}, ['id', 'name']],
            # ['videos', season_id, 'tags', 'summary'],
            # ['videos', season_id, ['creators', 'directors'], {'from': 0, 'to': 49}, ['id', 'name']],
            # ['videos', season_id, ['creators', 'directors'], 'summary'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'genres', {'from': 0, 'to': 1}, ['id', 'name']],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'genres', 'summary'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'interestingMoment', ART_MOMENT_SIZE_LARGE, 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'interestingMoment', ART_MOMENT_SIZE_SMALL, 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'boxarts', ART_BOX_SIZE_SMALL, 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'boxarts', ART_BOX_SIZE_LARGE, 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'boxarts', ART_BOX_SIZE_POSTER, 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'bb2OGLogo', ART_LOGO_SIZE, 'png'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'BGImages', ART_FANART_SIZE_EPISODE, 'jpg']
        ]
        response = self._path_request(paths=paths)
        return self._process_response(
            response=response,
            component='fetch_episodes_by_season')

    def refresh_session_data(self, account):
        """Reload the session data (profiles, user_data, api_data)

        Parameters
        ----------
        account : :obj:`dict` of :obj:`str`
            Dict containing an email, country & a password property
        """
        # load the profiles page (to verify the user)
        response = self._session_get(component='profiles')
        if response:
            # parse out the needed inline information
            page_data = self._parse_page_contents(content=response.content)
            if page_data is None:
                return False
            account_hash = self._generate_account_hash(account=account)
            self._save_data(filename=self.data_path + '_' + account_hash)
            return True
        return False

    def _path_request(self, paths):
        """
        Executes a post request against the shakti
        endpoint with falkor style payload

        Parameters
        ----------
        paths : :obj:`list` of :obj:`list`
            Payload with path querys for the Netflix Shakti API in falkor style

        Returns
        -------
        :obj:`requests.response`
            Response from a POST call made with Requests
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/javascript, */*',
        }

        data = json.dumps({
            'paths': paths,
            'authURL': self.user_data['authURL']
        })

        params = {
            'model': self.user_data['gpsModel']
        }

        response = self._session_post(
            component='shakti',
            type='api',
            params=params,
            headers=headers,
            data=data)
        if response:
            return response
        return None

    def _is_size_key(self, key):
        """
        Tiny helper that checks if a given key is called $size or size,
        as we need to check this often

        Parameters
        ----------
        key : :obj:`str`
            Key to check the value for

        Returns
        -------
        bool
            Key has a size value or not
        """
        return key == '$size' or key == 'size'

    def _get_api_url_for(self, component):
        """
        Tiny helper that builds the url for a requested API endpoint component

        Parameters
        ----------
        component : :obj:`str`
            Component endpoint to build the URL for

        Returns
        -------
        :obj:`str`
            API Url
        """
        api_root = self.api_data.get('API_ROOT', '')
        base_url = self.api_data.get('API_BASE_URL', '')
        build_id = self.api_data.get('BUILD_IDENTIFIER', '')
        url_component = self.urls.get(component, '')
        has_base_url = api_root.find(base_url) > -1
        api_url = api_root
        api_url += '/' if has_base_url is True else base_url + '/'
        api_url += build_id
        api_url += url_component
        return api_url

    def _get_document_url_for(self, component):
        """
        Tiny helper that builds the url for a
        requested document endpoint component

        Parameters
        ----------
        component : :obj:`str`
            Component endpoint to build the URL for

        Returns
        -------
        :obj:`str`
            Document Url
        """
        return self.base_url + self.urls[component]

    def _process_response(self, response, component):
        """Tiny helper to check responses for API requests

        Parameters
        ----------
        response : :obj:`requests.response`
            Response from a requests instance

        component : :obj:`str`
            Component endpoint

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str` or :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        if response is None:
            return {
                'error': True,
                'message': 'No response',
                'code': '500'
            }
        # check if we´re not authorized to make thios call
        if response.status_code == 401:
            return {
                'error': True,
                'message': 'Session invalid',
                'code': 401
            }
        # check if somethign else failed
        if response.status_code != 200:
            return {
                'error': True,
                'message': 'API call for "' + component + '" failed',
                'code': response.status_code
            }
        # everything´s fine if no parsing exception
        try:
            return response.json()
        except:
            exc = sys.exc_info()
            msg = 'Exception parsing JSON - {} {}'
            return {
                'error': True,
                'message': msg.format(exc[0], exc[1]),
                'code': '500'
            }

    def _update_my_list(self, video_id, operation):
        """Tiny helper to add & remove items from "my list"

        Parameters
        ----------
        video_id : :obj:`str`
            ID of the show/movie to be added

        operation : :obj:`str`
            Either "add" or "remove"

        Returns
        -------
        bool
            Operation successfull
        """
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/javascript, */*',
        }

        payload = json.dumps({
            'operation': operation,
            'videoId': int(video_id),
            'authURL': self.user_data.get('authURL')
        })

        response = self._session_post(
            component='update_my_list',
            type='api',
            headers=headers,
            data=payload)
        return response and response.status_code == 200

    def _init_session(self):
        try:
            self.session.close()
        except AttributeError:
            pass
        # start session, fake chrome on the current platform
        # (so that we get a proper widevine esn) & enable gzip
        self.session = session()
        self.session.headers.update({
            'User-Agent': get_user_agent(),
            'Accept-Encoding': 'gzip'
        })

    def _save_data(self, filename):
        """
        Tiny helper that stores session data from the session in a given file

        Parameters
        ----------
        filename : :obj:`str`
            Complete path/filename that determines where to store the data

        Returns
        -------
        bool
            Storage procedure was successfull
        """
        if not os.path.isdir(os.path.dirname(filename)):
            return False
        with open(filename, 'w') as f:
            f.truncate()
            pickle.dump({
                'user_data': self.user_data,
                'api_data': self.api_data,
                'profiles': self.profiles
            }, f)

    def _delete_data(self, path):
        """Tiny helper that deletes session data

        Parameters
        ----------
        filename : :obj:`str`
            Complete path/filename that determines where to delete the files

        """
        head, tail = os.path.split(path)
        for subdir, dirs, files in os.walk(head):
            for file in files:
                if tail in file:
                    os.remove(os.path.join(subdir, file))

    def _save_cookies(self, filename):
        """
        Stores cookies from the session in a file & mememory

        :param filename: path incl. filename of the cookie file
        :type filename: str
        :returns: bool -- Storing procedure successfull
        """
        if not os.path.isdir(os.path.dirname(filename)):
            return False
        with open(filename, 'w') as file_handle:
            _cookies = self.session.cookies._cookies
            jar = self.session.cookies
            file_handle.truncate()
            pickle.dump(_cookies, file_handle)
            self.parsed_cookies[filename] = (_cookies, jar)

    def _load_cookies(self, filename):
        """
        Loads cookies into the active session from a given file

        :param filename: path incl. filename of the cookie file
        :type filename: str
        :returns: bool or tuple -- Loading didn't work or parsed cookie data
        """
        # check if we have in memory cookies to spare some file i/o
        current_cookie = self.parsed_cookies.get(filename, None)
        if current_cookie is not None:
            self.nx_common.log(msg='Loading cookies from memory')
            self.session.cookies = current_cookie[1]
            return current_cookie

        # return if we haven't found a cookie file
        if not os.path.isfile(filename):
            self.nx_common.log(msg='No cookies found')
            return False

        # open the cookies file & set the loaded cookies
        with open(filename) as f:
            self.nx_common.log(msg='Loading cookies from file')
            _cookies = pickle.load(f)
            if _cookies:
                jar = cookies.RequestsCookieJar()
                jar._cookies = _cookies
                self.session.cookies = jar
                self.parsed_cookies[filename] = (_cookies, jar)
                return self.parsed_cookies.get(filename)
            else:
                return False

    def _delete_cookies(self, path):
        """
        Deletes cookie data

        :param path: path + filename for the cookie file
        :type path: string
        """
        self.parsed_cookies[path] = None
        head, tail = os.path.split(path)
        for subdir, dirs, files in os.walk(head):
            for file in files:
                if tail in file:
                    os.remove(os.path.join(subdir, file))
        self._init_session()

    def _generate_account_hash(self, account):
        """
        Generates a has for the given account (used for cookie/ud verification)

        :param account: email & password
        :type account: dict
        :returns: str -- Account data hash
        """
        return urlsafe_b64encode(account.get('email', 'NoMail'))

    def _session_post(self, component, type='document', data={}, headers={}, params={}):
        """
        Executes a get request using requests for the
        current session & measures the duration of that request

        Parameters
        ----------
        component : :obj:`str`
            Component to query

        type : :obj:`str`
            Is it a document or API request ('document' is default)

        data : :obj:`dict` of :obj:`str`
            Payload body as dict

        header : :obj:`dict` of :obj:`str`
            Additional headers as dict

        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
            :obj:`str`
                Contents of the field to match
        """
        url = self._get_document_url_for(component=component)
        if type != 'document':
            url = self._get_api_url_for(component=component)
        start = time()
        try:
            response = self.session.post(
                url=url,
                data=data,
                params=params,
                headers=headers,
                verify=self.verify_ssl)
        except SystemExit:
            self.nx_common.log(msg='[POST] system error arrived -> exiting')
            raise
        except:
            exc = sys.exc_info()
            self.nx_common.log(msg='[POST] Error {} {}'.format(exc[0], exc[1]))
            return None
        end = time()
        msg = '[POST] Req. for "' + url + '" took ' + str(end - start) + ' sec'
        self.nx_common.log(msg=msg)
        return response

    def _session_get(self, component, type='document', params={}):
        """
        Executes a get request using requests for the current session &
        measures the duration of that request

        Parameters
        ----------
        component : :obj:`str`
            Component to query

        type : :obj:`str`
            Is it a document or API request ('document' is default)

        params : :obj:`dict` of :obj:`str`
            Request params

        Returns
        -------
            :obj:`str`
                Contents of the field to match
        """
        url = self._get_document_url_for(component=component)
        if type != 'document':
            url = self._get_api_url_for(component=component)
        start = time()
        try:
            response = self.session.get(
                url=url,
                verify=self.verify_ssl,
                params=params)
        except SystemExit:
            self.nx_common.log(msg='[GET] system error arrived -> exiting')
            raise
        except:
            exc = sys.exc_info()
            self.nx_common.log(msg='[GET] Error {} {}'.format(exc[0], exc[1]))
            return None
        end = time()
        msg = '[GET] Req. for "' + url + '" took ' + str(end - start) + ' sec'
        self.nx_common.log(msg=msg)
        return response

    def _verfify_auth_and_profiles_data(self, data, profiles):
        """
        Checks if the authURL has at least a certain length &
        doesn't overrule a certain length & if the profiles dict exists
        Simple validity check for the sloppy data parser
        """
        auth_len = len(str(data.get('authURL', '')))
        if type(profiles) == dict:
            if auth_len > 10 and auth_len < 50:
                return True
        return False

    def _parse_esn_data(self, netflix_page_data):
        """Parse out the esn id data from the big chunk of dicts we got from
           parsing the JSOn-ish data from the netflix homepage

        Parameters
        ----------
        netflix_page_data : :obj:`list` of :obj:`dict`
            List of all the JSON-ish data that has been
            extracted from the Netflix homepage
            see: extract_inline_netflix_page_data

        Returns
        -------
            :obj:`str` of :obj:`str
            ESN, something like: NFCDCH-MC-D7D6F54LOPY8J416T72MQXX3RD20ME
        """
        # we generate an esn from device strings for android
        import subprocess
        import re
        try:
            manufacturer = subprocess.check_output(
                ['/system/bin/getprop', 'ro.product.manufacturer'])
            if manufacturer:
                esn = 'NFANDROID1-PRV-' if subprocess.check_output(
                    ['/system/bin/getprop', 'ro.build.characteristics']
                    ).strip(' \t\n\r') != 'tv' else 'NFANDROID2-PRV-'
                input = subprocess.check_output(
                    ['/system/bin/getprop', 'ro.nrdp.modelgroup']
                    ).strip(' \t\n\r')
                if not input:
                    esn += 'T-L3-'
                else:
                    esn += input + '-'
                esn += '{:=<5}'.format(manufacturer.strip(' \t\n\r').upper())
                input = subprocess.check_output(
                    ['/system/bin/getprop', 'ro.product.model'])
                esn += input.strip(' \t\n\r').replace(' ', '=').upper()
                esn = re.sub(r'[^A-Za-z0-9=-]', '=', esn)
                self.nx_common.log(msg='Android generated ESN:' + esn)
                return esn
        except OSError as e:
            self.nx_common.log(msg='Ignoring exception for non Android devices')

        # values are accessible via dict (sloppy parsing successfull)
        if type(netflix_page_data) == dict:
            return netflix_page_data.get('esn', '')
        return ''

    def _parse_page_contents(self, content):
        """
        Call all the parsers we need to extract all
        the session relevant data from the HTML page
        Directly assigns it to the NetflixSession instance
        """
        user_data, profiles = self.extract_inline_netflix_page_data(
            content=content)
        if user_data is None:
            return None
        self.user_data = user_data
        self.esn = self._parse_esn_data(user_data)
        if 'preferredLocale' in user_data:
            self.nx_common.set_setting('locale_id', user_data['preferredLocale']['id'])

        self.api_data = {
            'API_BASE_URL': user_data.get('API_BASE_URL'),
            'API_ROOT': user_data.get('API_ROOT'),
            'BUILD_IDENTIFIER': user_data.get('BUILD_IDENTIFIER'),
            'ICHNAEA_ROOT': user_data.get('ICHNAEA_ROOT'),
        }
        self.profiles = profiles
        self.nx_common.log(msg='Found ESN "' + self.esn + '"')
        return user_data
