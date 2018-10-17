# -*- coding: utf-8 -*-
"""Access to Netflix's Shakti API"""
from __future__ import unicode_literals

import resources.lib.common as common
from resources.lib.services.nfsession import NetflixSession

VIDEO_LIST_KEYS = ['user', 'genres', 'recommendations']
""":obj:`list` of :obj:`str`
Divide the users video lists into
3 different categories (for easier digestion)"""

def activate_profile(profile_id):
    """Activate the profile with the given ID"""
    common.make_call(NetflixSession.activate_profile, profile_id)

def logout():
    """Logout of the current account"""
    common.make_call(NetflixSession.logout)

def profiles():
    """Retrieve the list of available user profiles"""
    return common.make_call(NetflixSession.list_profiles)

def root_lists():
    """Retrieve initial video lists to display on homepage"""
    return parse_video_list_ids(
        common.make_call(
            NetflixSession.path_request,
            [
                [
                    'lolomo',
                    {'from': 0, 'to': 40},
                    ['displayName', 'context', 'id', 'index', 'length']
                ]
            ]))

def video_list_id_for_type(video_list_type):
    video_lists = root_lists()
    for video_list_id in video_lists['user']:
        if video_lists['user'][video_list_id]['name'] == video_list_type:
            return str(video_lists['user'][video_list_id]['id'])
    return {}

def video_list(video_list_id):
    """Retrieve a single video list"""
    pass

def seasons(tvshow_id):
    """Retrieve seasons of a TV show"""
    pass

def episodes(season_id):
    """Retrieve episodes of a season"""
    pass

def browse_genre(genre_id):
    """Retrieve video lists for a genre"""
    pass

def metadata(video_id):
    """Retrieve additional metadata for a video"""

def parse_video_list_ids(response_data):
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
    for key in VIDEO_LIST_KEYS:
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
            video_list_entry = parse_video_list_ids_entry(
                id=video_list_id,
                entry=video_list)
            if ctx == 'genre':
                video_list_ids['genres'].update(video_list_entry)
            elif ctx == 'similars' or ctx == 'becauseYouAdded':
                video_list_ids['recommendations'].update(video_list_entry)
            else:
                video_list_ids['user'].update(video_list_entry)
    return video_list_ids

def parse_video_list_ids_entry(id, entry):
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
