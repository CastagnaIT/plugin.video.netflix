# pylint: skip-file
# -*- coding: utf-8 -*-
# Module: NetflixSession
# Created on: 13.01.2017

import os
import sys
import json
from time import time
from urllib import quote, unquote
from re import compile as recompile
from base64 import urlsafe_b64encode
from requests import session, cookies
from utils import noop, get_user_agent
try:
   import cPickle as pickle
except:
   import pickle

FETCH_VIDEO_REQUEST_COUNT = 26

class NetflixSession:
    """Helps with login/session management of Netflix users & API data fetching"""

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
    """:obj:`dict` of :obj:`str` List of all static endpoints for HTML/JSON POST/GET requests"""

    video_list_keys = ['user', 'genres', 'recommendations']
    """:obj:`list` of :obj:`str` Divide the users video lists into 3 different categories (for easier digestion)"""

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
        'authURL',
        'BUILD_IDENTIFIER',
        'ICHNAEA_ROOT',
        'API_ROOT',
        'API_BASE_URL',
        'esn',
        'gpsModel',
        'countryOfSignup',
        'membershipStatus'
    ]

    def __init__(self, cookie_path, data_path, verify_ssl=True, log_fn=noop):
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
        self.log = log_fn
        self._init_session()

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
        self.log(msg='Parsing inline data...')
        items = self.page_items if items is None else items
        user_data = {'gpsModel': 'harris'}
        content = content.encode('utf-8').decode('string_escape')
        # find <script/> tag witch contains the 'reactContext' globals
        react_context = recompile('reactContext(?s)(.*);').findall(content)
        # iterate over all wanted item keys & try to fetch them
        for item in items:
            match = recompile(
                '"' + item + '":(.*?)"(.+?)"').findall(react_context[0])
            if len(match) > 0:
                _match = match[0][1]
                user_data.update({item: _match})
        # fetch profiles & avatars
        profiles = self.get_profiles(content=content)
        # get guid of active user
        for guid in profiles:
            if profiles[guid].get('isActive', False) is True:
                user_data['guid'] = guid

        # verify the data based on the authURL
        if self._verfify_auth_and_profiles_data(data=user_data, profiles=profiles) is not False:
            self.log(msg='Parsing inline data parsing successfull')
            return (user_data, profiles)
        self.log(msg='Parsing inline data failed')
        return (user_data, profiles)

    def get_profiles(self, content):
        """ADD ME"""
        profiles = {}
        # find everything between the profiles and the profiles_list property
        _pattern = '"profiles":(.*?)"profilesList'
        _profiles = recompile(_pattern).findall(content)
        # replace the last comma we found with nothing
        if len(_profiles):
            _profiles_string = _profiles[0][::-1].replace(',', '', 1)[::-1]
            # check if the last character is a closing bracket
            if _profiles_string[len(_profiles_string)-1] != '}':
                # if not, fix that
                _closing_pos = _profiles_string.rfind('}')+1
                _profiles_string = _profiles_string[:_closing_pos]
            _profiles_parsed = json.loads(_profiles_string)
            avatars = self.get_avatars(content=content)
            for guid in _profiles_parsed:
                if 'size' not in guid:
                    _profile = _profiles_parsed[guid].get('summary')
                    _name = _profile.get('avatarName')
                    _profile['avatar'] = avatars.get(_name)
                    profiles.update({guid: _profile})
        return profiles

    @classmethod
    def get_avatars(cls, content):
        """ADD ME"""
        avatars = {}
        # find everything between the avatars and the profiles property
        _pattern = '"avatars":(.*?)(.*)"profiles":'
        _avatars = recompile(_pattern).findall(content)
        # replace the last comma we found with nothing
        if len(_avatars):
            index = 1 if len(_avatars[0][0]) == 0 else 0
            _avatar_string = _avatars[0][index][::-1].replace(',', '', 1)[::-1]
            _avatars_parsed = json.loads(_avatar_string).get('nf')
            for _ava_key in _avatars_parsed:
                if 'size' not in _ava_key:
                    _images = _avatars_parsed[_ava_key].get('images', {})
                    _image = _images.get('byWidth', {}).get('320', {})
                    _url = _image.get('value')
                    avatars.update({_ava_key: _url})
        return avatars

    def is_logged_in(self, account):
        """Determines if a user is already logged in (with a valid cookie),
           by fetching the profile page with the current cookie & checking for profile(s)

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
        if cookies == False:
            return False

        # find the earliest expiration date in the cookies
        expires = 99999999999999999999
        cur_stamp = int(time())
        for domains in cookies:
            for domain in cookies[domains].keys():
                for cookie_key in cookies[domains][domain]:
                    exp = int(cookies[domains][domain][cookie_key].expires)
                    if expires > exp:
                        expires = exp
        if expires > cur_stamp:
            self.log(
                msg='Cookie expires: ' + str(expires) + ' / ' + str(cur_stamp))
            return True

        # load the profiles page (to verify the user)
        response = self._session_get(component='profiles')
        if response:
            # parse out the needed inline information
            user_data, profiles = self.extract_inline_netflix_page_data(content=response.text)
            self.profiles = profiles
            # if we have profiles, cookie is still valid
            if self.profiles:
                return True
        return False

    def logout(self):
        """Delete all cookies and session data

        Parameters
        ----------
        account : :obj:`dict` of :obj:`str`
            Dict containing an email, country & a password property

        """
        self._delete_cookies(path=self.cookie_path)
        self._delete_data(path=self.data_path)

    def login(self, account):
        """Try to log in a user with its credentials
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
            content=page.text)
        login_payload = {
            'email': account.get('email'),
            'password': account.get('password'),
            'rememberMe': 'true',
            'flow': 'websiteSignUp',
            'mode': 'login',
            'action': 'loginAction',
            'withFields': 'email,password,rememberMe,nextPage',
            'authURL': user_data.get('authURL'),
            'nextPage': ''
        }

        # perform the login
        login_response = self._session_post(component='login', data=login_payload)
        user_data = self._parse_page_contents(content=login_response.text)
        account_hash = self._generate_account_hash(account=account)
        # we know that the login was successfull if we find ???
        if user_data.get('membershipStatus') == 'CURRENT_MEMBER':
            # store cookies for later requests
            self._save_cookies(filename=self.cookie_path + '_' + account_hash)
            self._save_data(filename=self.data_path + '_' + account_hash)
            return True
        return False

    def switch_profile(self, profile_id, account):
        """Switch the user profile based on a given profile id

        Note: All available profiles & their ids can be found in the ´profiles´ property after a successfull login

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

        response = self._session_get(component='switch_profiles', type='api', params=payload)
        if (response == None or response.status_code != 200):
            return False

        account_hash = self._generate_account_hash(account=account)
        self.user_data['guid'] = profile_id;
        return self._save_data(filename=self.data_path + '_' + account_hash)

    def send_adult_pin(self, pin):
        """Send the adult pin to Netflix in case an adult rated video requests it

        Note: Once entered, it should last for the complete session (Not so sure about this)

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
        response = self._session_post(component='adult_pin', type='api', data=payload)
        pin_response = self._process_response(response=response, component=self._get_api_url_for(component='adult_pin'))
        if 'error' in pin_response.keys():
            self.log(msg='Pin error')
            self.log(msg=str(pin_response))
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
        ratun = int(rating)
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

        response = self._session_post(component='set_video_rating', type='api', params=params, headers=headers, data=payload)

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
        # this is the case when we fetch the lists via POST, not via a GET preflight request
        if 'value' in response_data.keys():
            response_data = response_data['value']

        # subcatogorize the lists by their context
        video_lists = response_data['lists']
        for video_list_id in video_lists.keys():
            video_list = video_lists[video_list_id]
            if video_list.get('context', False) != False:
                if video_list['context'] == 'genre':
                    video_list_ids['genres'].update(self.parse_video_list_ids_entry(id=video_list_id, entry=video_list))
                elif video_list['context'] == 'similars' or video_list['context'] == 'becauseYouAdded':
                    video_list_ids['recommendations'].update(self.parse_video_list_ids_entry(id=video_list_id, entry=video_list))
                else:
                    video_list_ids['user'].update(self.parse_video_list_ids_entry(id=video_list_id, entry=video_list))
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

    def parse_search_results(self, response_data):
        """Parse the list of search results, rip out the parts we need
           and extend it with detailed show informations

        Parameters
        ----------
        response_data : :obj:`dict` of :obj:`str`
            Parsed response JSON from the `fetch_search_results` call

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Search results in the format:

            {
                "70136140": {
                    "boxarts": "https://art-s.nflximg.net/0d7af/d5c72668c35d3da65ae031302bd4ae1bcc80d7af.jpg",
                    "detail_text": "Die legend\u00e4re und mit 13 Emmys nominierte Serie von Gene Roddenberry inspirierte eine ganze Generation.",
                    "id": "70136140",
                    "season_id": "70109435",
                    "synopsis": "Unter Befehl von Captain Kirk begibt sich die Besatzung des Raumschiffs Enterprise in die Tiefen des Weltraums, wo sie fremde Galaxien und neue Zivilisationen erforscht.",
                    "title": "Star Trek",
                    "type": "show"
                },
                "70158329": {
                    "boxarts": ...
                }
            }
        """
        search_results = {}
        raw_search_results = response_data['value']['videos']
        for entry_id in raw_search_results:
            if self._is_size_key(key=entry_id) == False:
                # fetch information about each show & build up a proper search results dictionary
                show = self.parse_show_list_entry(id=entry_id, entry=raw_search_results[entry_id])
                show[entry_id].update(self.parse_show_information(id=entry_id, response_data=self.fetch_show_information(id=entry_id, type=show[entry_id]['type'])))
                search_results.update(show)
        return search_results

    def parse_show_list_entry(self, id, entry):
        """Parse a show entry e.g. rip out the parts we need

        Parameters
        ----------
        response_data : :obj:`dict` of :obj:`str`
            Dictionary entry from the ´fetch_show_information´ call

        id : :obj:`str`
            Unique id of the video list

        Returns
        -------
        entry : :obj:`dict` of :obj:`dict` of :obj:`str`
            Show list entry in the format:

            {
                "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568382": {
                    "id": "3589e2c6-ca3b-48b4-a72d-34f2c09ffbf4_11568382",
                    "title": "Enterprise",
                    "boxarts": "https://art-s.nflximg.net/.../smth.jpg",
                    "type": "show"
                }
            }
        """
        return {
            id: {
                'id': id,
                'title': entry['title'],
                'boxarts': entry['boxarts']['_342x192']['jpg']['url'],
                'type': entry['summary']['type']
            }
        }

    def parse_video_list(self, response_data):
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
                      "big": "https://art-s.nflximg.net/5e7d3/b3b48749843fd3a36db11c319ffa60f96b55e7d3.jpg",
                      "small": "https://art-s.nflximg.net/57543/a039845c2eb9186dc26019576d895bf5a1957543.jpg"
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
                    "interesting_moment": "https://art-s.nflximg.net/09544/ed4b3073394b4469fb6ec22b9df81a4f5cb09544.jpg",
                    "list_id": "9588df32-f957-40e4-9055-1f6f33b60103_46891306",
                    "maturity": {
                      "board": "FSK",
                      "description": "Nur f\u00fcr Erwachsene geeignet.",
                      "level": 1000,
                      "value": "18"
                    },
                    "quality": "540",
                    "rating": 3.1707757,
                    "regular_synopsis": "Ein Spielzeughersteller erweckt aus Versehen die Seele der M\u00f6rderpuppe Chucky erneut zum Leben, die sich unmittelbar wieder ihren m\u00f6rderischen Aktivit\u00e4ten zuwendet.",
                    "runtime": 5028,
                    "seasons_count": null,
                    "seasons_label": null,
                    "synopsis": "Die allseits beliebte, von D\u00e4monen besessene M\u00f6rderpuppe ist wieder da und verbreitet erneut Horror und Schrecken.",
                    "tags": [
                      "Brutal",
                      "Spannend"
                    ],
                    "title": "Chucky 2 \u2013 Die M\u00f6rderpuppe ist wieder da",
                    "type": "movie",
                    "watched": false,
                    "year": 1990
                },
                "80011356": {
                    "artwork": null,
                    "boxarts": {
                      "big": "https://art-s.nflximg.net/7c10d/5dcc3fc8f08487e92507627068cfe26ef727c10d.jpg",
                      "small": "https://art-s.nflximg.net/5bc0e/f3be361b8c594929062f90a8d9c6eb57fb75bc0e.jpg"
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
                    "interesting_moment": "https://art-s.nflximg.net/0188e/19cd705a71ee08c8d2609ae01cd8a97a86c0188e.jpg",
                    "list_id": "9588df32-f957-40e4-9055-1f6f33b60103_46891306",
                    "maturity": {
                      "board": "FSF",
                      "description": "Geeignet ab 12 Jahren.",
                      "level": 80,
                      "value": "12"
                    },
                    "quality": "720",
                    "rating": 4.4394655,
                    "regular_synopsis": "Comedy-Serie \u00fcber die Erlebnisse eines Tatortreinigers, der seine schmutzige Arbeit erst beginnen kann, wenn die Polizei die Tatortanalyse abgeschlossen hat.",
                    "runtime": null,
                    "seasons_count": 5,
                    "seasons_label": "5 Staffeln",
                    "synopsis": "In den meisten Krimiserien werden Mordf\u00e4lle auf faszinierende und spannende Weise gel\u00f6st. Diese Serie ist anders.",
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
        video_list = {};
        raw_video_list = response_data['value']
        netflix_list_id = self.parse_netflix_list_id(video_list=raw_video_list);
        for video_id in raw_video_list['videos']:
            if self._is_size_key(key=video_id) == False:
                video_list.update(self.parse_video_list_entry(id=video_id, list_id=netflix_list_id, video=raw_video_list['videos'][video_id], persons=raw_video_list['person'], genres=raw_video_list['genres']))
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
                  "big": "https://art-s.nflximg.net/5e7d3/b3b48749843fd3a36db11c319ffa60f96b55e7d3.jpg",
                  "small": "https://art-s.nflximg.net/57543/a039845c2eb9186dc26019576d895bf5a1957543.jpg"
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
                "interesting_moment": "https://art-s.nflximg.net/09544/ed4b3073394b4469fb6ec22b9df81a4f5cb09544.jpg",
                "list_id": "9588df32-f957-40e4-9055-1f6f33b60103_46891306",
                "maturity": {
                  "board": "FSK",
                  "description": "Nur f\u00fcr Erwachsene geeignet.",
                  "level": 1000,
                  "value": "18"
                },
                "quality": "540",
                "rating": 3.1707757,
                "regular_synopsis": "Ein Spielzeughersteller erweckt aus Versehen die Seele der M\u00f6rderpuppe Chucky erneut zum Leben, die sich unmittelbar wieder ihren m\u00f6rderischen Aktivit\u00e4ten zuwendet.",
                "runtime": 5028,
                "seasons_count": null,
                "seasons_label": null,
                "synopsis": "Die allseits beliebte, von D\u00e4monen besessene M\u00f6rderpuppe ist wieder da und verbreitet erneut Horror und Schrecken.",
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
        return {
            id: {
                'id': id,
                'list_id': list_id,
                'title': video['title'],
                'synopsis': video['synopsis'],
                'regular_synopsis': video['regularSynopsis'],
                'type': video['summary']['type'],
                'rating': video['userRating'].get('average', 0) if video['userRating'].get('average', None) != None else video['userRating'].get('predicted', 0),
                'episode_count': season_info['episode_count'],
                'seasons_label': season_info['seasons_label'],
                'seasons_count': season_info['seasons_count'],
                'in_my_list': video['queue']['inQueue'],
                'year': video['releaseYear'],
                'runtime': self.parse_runtime_for_video(video=video),
                'watched': video.get('watched', None),
                'tags': self.parse_tags_for_video(video=video),
                'genres': self.parse_genres_for_video(video=video, genres=genres),
                'quality': self.parse_quality_for_video(video=video),
                'cast': self.parse_cast_for_video(video=video, persons=persons),
                'directors': self.parse_directors_for_video(video=video, persons=persons),
                'creators': self.parse_creators_for_video(video=video, persons=persons),
                'maturity': {
                    'board': None if 'board' not in video['maturity']['rating'].keys() else video['maturity']['rating']['board'],
                    'value': None if 'value' not in video['maturity']['rating'].keys() else video['maturity']['rating']['value'],
                    'description': None if 'maturityDescription' not in video['maturity']['rating'].keys() else video['maturity']['rating']['maturityDescription'],
                    'level': None if 'maturityLevel' not in video['maturity']['rating'].keys() else video['maturity']['rating']['maturityLevel']
                },
                'boxarts': {
                    'small': video['boxarts']['_342x192']['jpg']['url'],
                    'big': video['boxarts']['_1280x720']['jpg']['url']
                },
                'interesting_moment': None if 'interestingMoment' not in video.keys() else video['interestingMoment']['_665x375']['jpg']['url'],
                'artwork': video['artWorkByType']['BILLBOARD']['_1280x720']['jpg']['url'],
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
            if self._is_size_key(key=person_key) == False and person_key != 'summary':
                for creator_key in dict(video['creators']).keys():
                    if self._is_size_key(key=creator_key) == False and creator_key != 'summary':
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
            if self._is_size_key(key=person_key) == False and person_key != 'summary':
                for director_key in dict(video['directors']).keys():
                    if self._is_size_key(key=director_key) == False and director_key != 'summary':
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
            if self._is_size_key(key=person_key) == False and person_key != 'summary':
                for cast_key in dict(video['cast']).keys():
                    if self._is_size_key(key=cast_key) == False and cast_key != 'summary':
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

        for video_genre_key, video_genre in video['genres'].iteritems():
            if self._is_size_key(video_genre_key) == False and video_genre_key != 'summary':
                name = genres.get(video_genre[1], {}).get('name')

                if name:
                    video_genres.append(name)

        return video_genres

    def parse_tags_for_video(self, video):
        """Parses a nested list of tags, removes the not needed meta information & returns a raw string list

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
        for tag_key in dict(video['tags']).keys():
            if self._is_size_key(key=tag_key) == False and tag_key != 'summary':
                tags.append(video['tags'][tag_key]['name'])
        return tags

    def parse_season_information_for_video(self, video):
        """Checks if the fiven video is a show (series) and returns season & episode information

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
        if video['delivery']['hasHD']:
            quality = '1080'
        if video['delivery']['hasUltraHD']:
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
        if video['summary']['type'] != 'show':
            runtime = video['runtime']
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
            for video_id in video_list['lists']:
                if self._is_size_key(key=video_id) == False:
                    netflix_list_id = video_id;
        return netflix_list_id

    def parse_show_information(self, id, response_data):
        """Parse extended show information (synopsis, seasons, etc.)

        Parameters
        ----------
        id : :obj:`str`
            Video id

        response_data : :obj:`dict` of :obj:`str`
            Parsed response JSON from the `fetch_show_information` call

        Returns
        -------
        entry : :obj:`dict` of :obj:`str`
        Show information in the format:
            {
                "season_id": "80113084",
                "synopsis": "Aus verzweifelter Geldnot versucht sich der Familienvater und Drucker Jochen als Geldf\u00e4lscher und rutscht dabei immer mehr in die dunkle Welt des Verbrechens ab."
                "detail_text": "I´m optional"
            }
        """
        show = {}
        raw_show = response_data['value']['videos'][id]
        show.update({'synopsis': raw_show['regularSynopsis']})

        if 'evidence' in raw_show and raw_show.get('evidence') is not None and raw_show.get('evidence').get('value') is not None:
            show.update({'detail_text': raw_show.get('evidence', {}).get('value', {}).get('text', '')})
        if 'seasonList' in raw_show:
            show.update({'season_id': raw_show.get('seasonList', {}).get('current', [])[1]})
        return show

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
                      "big": "https://art-s.nflximg.net/5e7d3/b3b48749843fd3a36db11c319ffa60f96b55e7d3.jpg",
                      "small": "https://art-s.nflximg.net/57543/a039845c2eb9186dc26019576d895bf5a1957543.jpg"
                    },
                    "interesting_moment": "https://art-s.nflximg.net/09544/ed4b3073394b4469fb6ec22b9df81a4f5cb09544.jpg"
                },
                "80113085": {
                    "id": 80113085,
                    "text": "Season 2",
                    "shortName": "St. 2",
                    "boxarts": {
                      "big": "https://art-s.nflximg.net/5e7d3/b3b48749843fd3a36db11c319ffa60f96b55e7d3.jpg",
                      "small": "https://art-s.nflximg.net/57543/a039845c2eb9186dc26019576d895bf5a1957543.jpg"
                    },
                    "interesting_moment": "https://art-s.nflximg.net/09544/ed4b3073394b4469fb6ec22b9df81a4f5cb09544.jpg"
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
            if self._is_size_key(key=idx) == False and idx != 'summary':
                sorting[int(season_list_entry[1])] = int(idx)

        seasons = {}

        for season in raw_seasons['seasons']:
            if self._is_size_key(key=season) == False:
                seasons.update(self._parse_season_entry(season=raw_seasons['seasons'][season], video=video, sorting=sorting))
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
                      "big": "https://art-s.nflximg.net/5e7d3/b3b48749843fd3a36db11c319ffa60f96b55e7d3.jpg",
                      "small": "https://art-s.nflximg.net/57543/a039845c2eb9186dc26019576d895bf5a1957543.jpg"
                    },
                    "interesting_moment": "https://art-s.nflximg.net/09544/ed4b3073394b4469fb6ec22b9df81a4f5cb09544.jpg"
                }
            }
        """
        return {
            season['summary']['id']: {
                'idx': sorting[season['summary']['id']],
                'id': season['summary']['id'],
                'text': season['summary']['name'],
                'shortName': season['summary']['shortName'],
                'boxarts': {
                    'small': video['boxarts']['_342x192']['jpg']['url'],
                    'big': video['boxarts']['_1280x720']['jpg']['url']
                },
                'interesting_moment': video['interestingMoment']['_665x375']['jpg']['url'],
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
            "banner": "https://art-s.nflximg.net/63a36/c7fdfe6604ef2c22d085ac5dca5f69874e363a36.jpg",
            "duration": 1387,
            "episode": 1,
            "fanart": "https://art-s.nflximg.net/74e02/e7edcc5cc7dcda1e94d505df2f0a2f0d22774e02.jpg",
            "genres": [
              "Serien",
              "Comedyserien"
            ],
            "id": 70251729,
            "mediatype": "episode",
            "mpaa": "FSK 16",
            "my_list": false,
            "playcount": 0,
            "plot": "Als die Griffins und andere Einwohner von Quahog in die Villa von James Woods eingeladen werden, muss pl\u00f6tzlich ein Mord aufgekl\u00e4rt werden.",
            "poster": "https://art-s.nflximg.net/72fd6/57088715e8d436fdb6986834ab39124b0a972fd6.jpg",
            "rating": 3.9111512,
            "season": 9,
            "thumb": "https://art-s.nflximg.net/be686/07680670a68da8749eba607efb1ae37f9e3be686.jpg",
            "title": "Und dann gab es weniger (Teil 1)",
            "year": 2010,
            "bookmark": -1
          },
          "70251730": {
            "banner": "https://art-s.nflximg.net/63a36/c7fdfe6604ef2c22d085ac5dca5f69874e363a36.jpg",
            "duration": 1379,
            "episode": 2,
            "fanart": "https://art-s.nflximg.net/c472c/6c10f9578bf2c1d0a183c2ccb382931efcbc472c.jpg",
            "genres": [
              "Serien",
              "Comedyserien"
            ],
            "id": 70251730,
            "mediatype": "episode",
            "mpaa": "FSK 16",
            "my_list": false,
            "playcount": 1,
            "plot": "Wer ist der M\u00f6rder? Nach zahlreichen Morden wird immer wieder jemand anderes verd\u00e4chtigt.",
            "poster": "https://art-s.nflximg.net/72fd6/57088715e8d436fdb6986834ab39124b0a972fd6.jpg",
            "rating": 3.9111512,
            "season": 9,
            "thumb": "https://art-s.nflximg.net/15a08/857d59126641987bec302bb147a802a00d015a08.jpg",
            "title": "Und dann gab es weniger (Teil 2)",
            "year": 2010,
            "bookmark": 1234
          },
        }
        """
        episodes = {}
        raw_episodes = response_data['value']['videos']
        for episode_id in raw_episodes:
            if self._is_size_key(key=episode_id) == False:
                if (raw_episodes[episode_id]['summary']['type'] == 'episode'):
                    episodes.update(self.parse_episode(episode=raw_episodes[episode_id], genres=response_data['value']['genres']))
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
            "banner": "https://art-s.nflximg.net/63a36/c7fdfe6604ef2c22d085ac5dca5f69874e363a36.jpg",
            "duration": 1387,
            "episode": 1,
            "fanart": "https://art-s.nflximg.net/74e02/e7edcc5cc7dcda1e94d505df2f0a2f0d22774e02.jpg",
            "genres": [
              "Serien",
              "Comedyserien"
            ],
            "id": 70251729,
            "mediatype": "episode",
            "mpaa": "FSK 16",
            "my_list": false,
            "playcount": 0,
            "plot": "Als die Griffins und andere Einwohner von Quahog in die Villa von James Woods eingeladen werden, muss pl\u00f6tzlich ein Mord aufgekl\u00e4rt werden.",
            "poster": "https://art-s.nflximg.net/72fd6/57088715e8d436fdb6986834ab39124b0a972fd6.jpg",
            "rating": 3.9111512,
            "season": 9,
            "thumb": "https://art-s.nflximg.net/be686/07680670a68da8749eba607efb1ae37f9e3be686.jpg",
            "title": "Und dann gab es weniger (Teil 1)",
            "year": 2010,
            "bookmark": 1234
          },
        }
        """
        mpaa = ''
        if episode.get('maturity', None) is not None:
            if episode['maturity'].get('board', None) is not None and episode['maturity'].get('value', None) is not None:
                mpaa = str(episode['maturity'].get('board', '').encode('utf-8')) + '-' + str(episode['maturity'].get('value', '').encode('utf-8'))

        return {
            episode['summary']['id']: {
                'id': episode['summary']['id'],
                'episode': episode['summary']['episode'],
                'season': episode['summary']['season'],
                'plot': episode['info']['synopsis'],
                'duration': episode['info']['runtime'],
                'title': episode['info']['title'],
                'year': episode['info']['releaseYear'],
                'genres': self.parse_genres_for_video(video=episode, genres=genres),
                'mpaa': mpaa,
                'maturity': episode['maturity'],
                'playcount': (0, 1)[episode['watched']],
                'rating': episode['userRating'].get('average', 0) if episode['userRating'].get('average', None) != None else episode['userRating'].get('predicted', 0),
                'thumb': episode['info']['interestingMoments']['url'],
                'fanart': episode['interestingMoment']['_1280x720']['jpg']['url'],
                'poster': episode['boxarts']['_1280x720']['jpg']['url'],
                'banner': episode['boxarts']['_342x192']['jpg']['url'],
                'mediatype': {'episode': 'episode', 'movie': 'movie'}[episode['summary']['type']],
                'my_list': episode['queue']['inQueue'],
                'bookmark': episode['bookmarkPosition']
            }
        }

    def fetch_video_list_ids(self, list_from=0, list_to=50):
        """Fetches the JSON with detailed information based on the lists on the landing page (browse page) of Netflix

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
            ['lolomo', {'from': list_from, 'to': list_to}, ['displayName', 'context', 'id', 'index', 'length']]
        ]

        response = self._path_request(paths=paths)
        return self._process_response(response=response, component='Video list ids')

    def fetch_search_results(self, search_str, list_from=0, list_to=10):
        """Fetches the JSON which contains the results for the given search query

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
        # properly encode the search string
        encoded_search_string = quote(search_str)

        paths = [
            ['search', encoded_search_string, 'titles', {'from': list_from, 'to': list_to}, ['summary', 'title']],
            ['search', encoded_search_string, 'titles', {'from': list_from, 'to': list_to}, 'boxarts', '_342x192', 'jpg'],
            ['search', encoded_search_string, 'titles', ['id', 'length', 'name', 'trackIds', 'requestId']],
            ['search', encoded_search_string, 'suggestions', 0, 'relatedvideos', {'from': list_from, 'to': list_to}, ['summary', 'title']],
            ['search', encoded_search_string, 'suggestions', 0, 'relatedvideos', {'from': list_from, 'to': list_to}, 'boxarts', '_342x192', 'jpg'],
            ['search', encoded_search_string, 'suggestions', 0, 'relatedvideos', ['id', 'length', 'name', 'trackIds', 'requestId']]
        ]
        response = self._path_request(paths=paths)
        return self._process_response(response=response, component='Search results')

    def fetch_video_list(self, list_id, list_from=0, list_to=FETCH_VIDEO_REQUEST_COUNT):
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
        paths = [
            ['lists', list_id, {'from': list_from, 'to': list_to}, ['summary', 'title', 'synopsis', 'regularSynopsis', 'evidence', 'queue', 'episodeCount', 'info', 'maturity', 'runtime', 'seasonCount', 'releaseYear', 'userRating', 'numSeasonsLabel', 'bookmarkPosition', 'watched', 'delivery']],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'cast', {'from': 0, 'to': 15}, ['id', 'name']],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'cast', 'summary'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'genres', {'from': 0, 'to': 5}, ['id', 'name']],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'genres', 'summary'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'tags', {'from': 0, 'to': 9}, ['id', 'name']],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'tags', 'summary'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, ['creators', 'directors'], {'from': 0, 'to': 49}, ['id', 'name']],
            ['lists', list_id, {'from': list_from, 'to': list_to}, ['creators', 'directors'], 'summary'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'bb2OGLogo', '_400x90', 'png'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'boxarts', '_342x192', 'jpg'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'boxarts', '_1280x720', 'jpg'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'storyarts', '_1632x873', 'jpg'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'interestingMoment', '_665x375', 'jpg'],
            ['lists', list_id, {'from': list_from, 'to': list_to}, 'artWorkByType', 'BILLBOARD', '_1280x720', 'jpg']
        ]

        response = self._path_request(paths=paths)
        return self._process_response(response=response, component='Video list')

    def fetch_video_list_information(self, video_ids):
        """Fetches the JSON which contains the detail information of a list of given video ids

        Parameters
        ----------
        video_ids : :obj:`list` of :obj:`str`
            List of video ids to fetch detail data for

        Returns
        -------
        :obj:`dict` of :obj:`dict` of :obj:`str`
            Raw Netflix API call response or api call error
        """
        paths = []
        for video_id in video_ids:
            paths.append(['videos', video_id, ['summary', 'title', 'synopsis', 'regularSynopsis', 'evidence', 'queue', 'episodeCount', 'info', 'maturity', 'runtime', 'seasonCount', 'releaseYear', 'userRating', 'numSeasonsLabel', 'bookmarkPosition', 'watched', 'delivery']])
            paths.append(['videos', video_id, 'cast', {'from': 0, 'to': 15}, ['id', 'name']])
            paths.append(['videos', video_id, 'cast', 'summary'])
            paths.append(['videos', video_id, 'genres', {'from': 0, 'to': 5}, ['id', 'name']])
            paths.append(['videos', video_id, 'genres', 'summary'])
            paths.append(['videos', video_id, 'tags', {'from': 0, 'to': 9}, ['id', 'name']])
            paths.append(['videos', video_id, 'tags', 'summary'])
            paths.append(['videos', video_id, ['creators', 'directors'], {'from': 0, 'to': 49}, ['id', 'name']])
            paths.append(['videos', video_id, ['creators', 'directors'], 'summary'])
            paths.append(['videos', video_id, 'bb2OGLogo', '_400x90', 'png'])
            paths.append(['videos', video_id, 'boxarts', '_342x192', 'jpg'])
            paths.append(['videos', video_id, 'boxarts', '_1280x720', 'jpg'])
            paths.append(['videos', video_id, 'storyarts', '_1632x873', 'jpg'])
            paths.append(['videos', video_id, 'interestingMoment', '_665x375', 'jpg'])
            paths.append(['videos', video_id, 'artWorkByType', 'BILLBOARD', '_1280x720', 'jpg'])

        response = self._path_request(paths=paths)
        return self._process_response(response=response, component='fetch_video_list_information')

    def fetch_metadata(self, id):
        """Fetches the JSON which contains the metadata for a given show/movie or season id

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
        response = self._session_get(component='metadata', params=payload, type='api')
        return self._process_response(response=response, component=self._get_api_url_for(component='metadata'))

    def fetch_show_information(self, id, type):
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
            paths = [['videos', id, ['requestId', 'regularSynopsis', 'evidence']]]
        response = self._path_request(paths=paths)
        return self._process_response(response=response, component='Show information')

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
            ['videos', id, 'boxarts',  '_342x192', 'jpg'],
            ['videos', id, 'boxarts', '_1280x720', 'jpg'],
            ['videos', id, 'storyarts',  '_1632x873', 'jpg'],
            ['videos', id, 'interestingMoment', '_665x375', 'jpg']
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
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, ['summary', 'queue', 'info', 'maturity', 'userRating', 'bookmarkPosition', 'creditOffset', 'watched', 'delivery']],
            #['videos', season_id, 'cast', {'from': 0, 'to': 15}, ['id', 'name']],
            #['videos', season_id, 'cast', 'summary'],
            #['videos', season_id, 'genres', {'from': 0, 'to': 5}, ['id', 'name']],
            #['videos', season_id, 'genres', 'summary'],
            #['videos', season_id, 'tags', {'from': 0, 'to': 9}, ['id', 'name']],
            #['videos', season_id, 'tags', 'summary'],
            #['videos', season_id, ['creators', 'directors'], {'from': 0, 'to': 49}, ['id', 'name']],
            #['videos', season_id, ['creators', 'directors'], 'summary'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'genres', {'from': 0, 'to': 1}, ['id', 'name']],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'genres', 'summary'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'interestingMoment', '_1280x720', 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'interestingMoment', '_665x375', 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'boxarts', '_342x192', 'jpg'],
            ['seasons', season_id, 'episodes', {'from': list_from, 'to': list_to}, 'boxarts', '_1280x720', 'jpg']
        ]
        response = self._path_request(paths=paths)
        return self._process_response(response=response, component='fetch_episodes_by_season')

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
            page_data = self._parse_page_contents(content=response.text)
            if page_data is None:
                return False
            account_hash = self._generate_account_hash(account=account)
            self._save_data(filename=self.data_path + '_' + account_hash)
            return True
        return False

    def _path_request(self, paths):
        """Executes a post request against the shakti endpoint with Falcor style payload

        Parameters
        ----------
        paths : :obj:`list` of :obj:`list`
            Payload with path querys for the Netflix Shakti API in Falcor style

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

        response = self._session_post(component='shakti', type='api', params=params, headers=headers, data=data)
        if response:
            return response
        return None

    def _is_size_key(self, key):
        """Tiny helper that checks if a given key is called $size or size, as we need to check this often

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
        """Tiny helper that builds the url for a requested API endpoint component

        Parameters
        ----------
        component : :obj:`str`
            Component endpoint to build the URL for

        Returns
        -------
        :obj:`str`
            API Url
        """
        if self.api_data['API_ROOT'].find(self.api_data['API_BASE_URL']) > -1:
            return self.api_data['API_ROOT'] + '/' + self.api_data['BUILD_IDENTIFIER'] + self.urls[component]
        else:
            return self.api_data['API_ROOT'] + self.api_data['API_BASE_URL'] + '/' + self.api_data['BUILD_IDENTIFIER'] + self.urls[component]

    def _get_document_url_for(self, component):
        """Tiny helper that builds the url for a requested document endpoint component

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
        if response == None:
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
            return {
                'error': True,
                'message': 'Exception parsing JSON - {} {}'.format(exc[0],exc[1]),
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
            'authURL': self.user_data['authURL']
        })

        response = self._session_post(component='update_my_list', type='api', headers=headers, data=payload)

        if response and response.status_code == 200:
            return True
        return False

    def _init_session(self):
        try:
            self.session.close()
        except AttributeError:
            pass
        # start session, fake chrome on the current platform (so that we get a proper widevine esn) & enable gzip
        self.session = session()
        self.session.headers.update({
            'User-Agent': get_user_agent(),
            'Accept-Encoding': 'gzip'
        })

    def _save_data(self, filename):
        """Tiny helper that stores session data from the session in a given file

        Parameters
        ----------
        filename : :obj:`str`
            Complete path incl. filename that determines where to store the cookie

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
            Complete path incl. filename that determines where to delete the files

        """
        head, tail = os.path.split(path)
        for subdir, dirs, files in os.walk(head):
            for file in files:
                if tail in file:
                    os.remove(os.path.join(subdir, file))

    def _save_cookies(self, filename):
        """Tiny helper that stores cookies from the session in a given file

        Parameters
        ----------
        filename : :obj:`str`
            Complete path incl. filename that determines where to store the cookie

        Returns
        -------
        bool
            Storage procedure was successfull
        """
        if not os.path.isdir(os.path.dirname(filename)):
            return False
        with open(filename, 'w') as f:
            f.truncate()
            pickle.dump(self.session.cookies._cookies, f)

    def _load_cookies(self, filename):
        """Tiny helper that loads cookies into the active session from a given file

        Parameters
        ----------
        filename : :obj:`str`
            Complete path incl. filename that determines where to load the cookie from

        Returns
        -------
        bool
            Load procedure was successfull
        """
        if not os.path.isfile(filename):
            return False

        with open(filename) as f:
            _cookies = pickle.load(f)
            if _cookies:
                jar = cookies.RequestsCookieJar()
                jar._cookies = _cookies
                self.session.cookies = jar
                return _cookies
            else:
                return False

    def _delete_cookies(self, path):
        """Tiny helper that deletes cookie data

        Parameters
        ----------
        filename : :obj:`str`
            Complete path incl. filename that determines where to delete the files

        """
        head, tail = os.path.split(path)
        for subdir, dirs, files in os.walk(head):
            for file in files:
                if tail in file:
                    os.remove(os.path.join(subdir, file))
        self._init_session()

    def _generate_account_hash(self, account):
        """Generates a has for the given account (used for cookie verification)

        Parameters
        ----------
        account : :obj:`dict` of :obj:`str`
            Dict containing an email, country & a password property

        Returns
        -------
        :obj:`str`
            Account data hash
        """
        return urlsafe_b64encode(account['email'])

    def _session_post(self, component, type='document', data={}, headers={}, params={}):
        """Executes a get request using requests for the current session & measures the duration of that request

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
        url = self._get_document_url_for(component=component) if type == 'document' else self._get_api_url_for(component=component)
        start = time()
        try:
            response = self.session.post(url=url, data=data, params=params, headers=headers, verify=self.verify_ssl)
        except:
            exc = sys.exc_info()
            self.log(msg='[POST] Error {} {}'.format(exc[0],exc[1]))
            return None
        end = time()
        self.log(msg='[POST] Request for "' + url + '" took ' + str(end - start) + ' seconds')
        return response

    def _session_get(self, component, type='document', params={}):
        """Executes a get request using requests for the current session & measures the duration of that request

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
        url = self._get_document_url_for(component=component) if type == 'document' else self._get_api_url_for(component=component)
        start = time()
        try:
            response = self.session.get(url=url, verify=self.verify_ssl, params=params)
        except:
            exc = sys.exc_info()
            self.log(msg='[GET] Error {} {}'.format(exc[0],exc[1]))
            return None
        end = time()
        self.log(msg='[GET] Request for "' + url + '" took ' + str(end - start) + ' seconds')
        return response

    def _verfify_auth_and_profiles_data(self, data, profiles):
        """
        Checks if the authURL has at least a certain length &
        doesn't overrule a certain length & if the profiles dict exists
        Simple validity check for the sloppy data parser
        """
        if type(profiles) == dict:
            if len(str(data.get('authURL', ''))) > 10 and len(str(data.get('authURL', ''))) < 50:
                return True
        return False

    def _parse_esn_data(self, netflix_page_data):
        """Parse out the esn id data from the big chunk of dicts we got from
           parsing the JSOn-ish data from the netflix homepage

        Parameters
        ----------
        netflix_page_data : :obj:`list` of :obj:`dict`
            List of all the JSON-ish data that has been extracted from the Netflix homepage
            see: extract_inline_netflix_page_data

        Returns
        -------
            :obj:`str` of :obj:`str
            ESN, something like: NFCDCH-MC-D7D6F54LOPY8J416T72MQXX3RD20ME
        """
        # we generate an esn from device strings for android
        import subprocess
        try:
            manufacturer = subprocess.check_output(["/system/bin/getprop", "ro.product.manufacturer"])
            if manufacturer:
                esn = 'NFANDROID1-PRV-'
                input = subprocess.check_output(["/system/bin/getprop", "ro.nrdp.modelgroup"])
                if not input:
                    esn = esn + 'T-L3-'
                else:
                    esn = esn + input.strip(' \t\n\r') + '-'
                esn = esn + '{:5}'.format(manufacturer.strip(' \t\n\r').upper())
                input = subprocess.check_output(["/system/bin/getprop" ,"ro.product.model"])
                esn = esn + input.strip(' \t\n\r').replace(' ', '=').upper()
                self.log(msg='Android generated ESN:' + esn)
                return esn
        except OSError as e:
            self.log(msg='Ignoring exception for non Android devices')

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
        user_data, profiles = self.extract_inline_netflix_page_data(content=content)
        if user_data is None:
            return None
        self.user_data = user_data
        self.esn = user_data.get('esn')
        self.api_data = {
            'API_BASE_URL': user_data.get('API_BASE_URL'),
            'API_ROOT': user_data.get('API_ROOT'),
            'BUILD_IDENTIFIER': user_data.get('BUILD_IDENTIFIER'),
            'ICHNAEA_ROOT': user_data.get('ICHNAEA_ROOT'),
        }
        self.profiles = profiles
        self.log(msg='Found ESN "' + self.esn + '"')
        return user_data
