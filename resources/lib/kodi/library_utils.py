# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Kodi library integration: helper utils

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import os
import random
from datetime import datetime, timedelta
from functools import wraps

import xbmc

from resources.lib import common
from resources.lib.common.exceptions import InvalidVideoId
from resources.lib.database.db_utils import VidLibProp
from resources.lib.globals import G
from resources.lib.kodi import nfo, ui
from resources.lib.utils.api_paths import PATH_REQUEST_SIZE_STD
from resources.lib.utils.logging import LOG, measure_exec_time_decorator

LIBRARY_HOME = 'library'
FOLDER_NAME_MOVIES = 'movies'
FOLDER_NAME_SHOWS = 'shows'
ILLEGAL_CHARACTERS = '[<|>|"|?|$|!|:|#|*|/|\\\\]'


def get_library_path():
    """Return the full path to the library"""
    return (G.ADDON.getSetting('customlibraryfolder')
            if G.ADDON.getSettingBool('enablelibraryfolder')
            else G.DATA_PATH)


def get_library_subfolders(folder_name, custom_lib_path=None):
    """Returns all the subfolders contained in a folder of library path"""
    section_path = common.join_folders_paths(custom_lib_path or get_library_path(), folder_name)
    return [common.join_folders_paths(section_path, folder)
            for folder
            in common.list_dir(section_path)[0]]


def insert_videoid_to_db(videoid, export_filename, nfo_export, exclude_update=False):
    """Add records to the database in relation to a videoid"""
    if videoid.mediatype == common.VideoId.EPISODE:
        G.SHARED_DB.set_tvshow(videoid.tvshowid, nfo_export, exclude_update)
        G.SHARED_DB.insert_season(videoid.tvshowid, videoid.seasonid)
        G.SHARED_DB.insert_episode(videoid.tvshowid, videoid.seasonid,
                                   videoid.value, export_filename)
    elif videoid.mediatype == common.VideoId.MOVIE:
        G.SHARED_DB.set_movie(videoid.value, export_filename, nfo_export)


def remove_videoid_from_db(videoid):
    """Removes records from database in relation to a videoid"""
    if videoid.mediatype == common.VideoId.MOVIE:
        G.SHARED_DB.delete_movie(videoid.value)
    elif videoid.mediatype == common.VideoId.EPISODE:
        G.SHARED_DB.delete_episode(videoid.tvshowid, videoid.seasonid, videoid.episodeid)


def is_videoid_in_db(videoid):
    """Return True if the video is in the database, else False"""
    if videoid.mediatype == common.VideoId.MOVIE:
        return G.SHARED_DB.movie_id_exists(videoid.value)
    if videoid.mediatype == common.VideoId.SHOW:
        return G.SHARED_DB.tvshow_id_exists(videoid.value)
    if videoid.mediatype == common.VideoId.SEASON:
        return G.SHARED_DB.season_id_exists(videoid.tvshowid,
                                            videoid.seasonid)
    if videoid.mediatype == common.VideoId.EPISODE:
        return G.SHARED_DB.episode_id_exists(videoid.tvshowid,
                                             videoid.seasonid,
                                             videoid.episodeid)
    raise InvalidVideoId(f'videoid {videoid} type not implemented')


def get_episode_title_from_path(file_path):
    filename = os.path.splitext(os.path.basename(file_path))[0]
    path = os.path.split(os.path.split(file_path)[0])[1]
    return f'{path} - {filename}'


def get_nfo_settings():
    """Get the NFO settings, confirmations may be requested to the user if necessary"""
    return nfo.NFOSettings()


def is_auto_update_library_running(show_prg_dialog):
    if G.SHARED_DB.get_value('library_auto_update_is_running', False):
        start_time = G.SHARED_DB.get_value('library_auto_update_start_time',
                                           datetime.utcfromtimestamp(0))
        if datetime.now() >= start_time + timedelta(hours=6):
            G.SHARED_DB.set_value('library_auto_update_is_running', False)
            LOG.warn('Canceling previous library update: duration >6 hours')
        else:
            if show_prg_dialog:
                ui.show_notification(common.get_local_string(30063))
            LOG.debug('Library auto update is already running')
            return True
    return False


@measure_exec_time_decorator(is_immediate=True)
def request_kodi_library_update(**kwargs):
    """Request to scan and/or clean the Kodi library database"""
    # Particular way to start Kodi library scan/clean (details on request_kodi_library_update in library_updater.py)
    if not kwargs:
        raise Exception('request_kodi_library_update: you must specify kwargs "scan=True" and/or "clean=True"')
    common.send_signal(common.Signals.REQUEST_KODI_LIBRARY_UPDATE, data=kwargs, non_blocking=True)


def request_kodi_library_scan_decorator(func):
    """
    A decorator to request the scan of Kodi library database (at the end of the operations)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        ret = func(*args, **kwargs)
        request_kodi_library_update(scan=True)
        return ret
    return wrapper


def is_show_excluded_from_auto_update(videoid):
    """Return true if the videoid is excluded from auto-update"""
    return G.SHARED_DB.get_tvshow_property(videoid.value, VidLibProp['exclude_update'], False)


def set_show_excluded_from_auto_update(videoid, is_excluded):
    """Set if a tvshow is excluded from auto-update"""
    G.SHARED_DB.set_tvshow_property(videoid.value, VidLibProp['exclude_update'], is_excluded)


def list_contents(perpetual_range_start):
    """Return a chunked list of all video IDs (movies, shows) contained in the add-on library database"""
    perpetual_range_start = int(perpetual_range_start) if perpetual_range_start else 0
    number_of_requests = 2
    video_id_list = G.SHARED_DB.get_all_video_id_list()
    count = 0
    chunked_video_list = []
    perpetual_range_selector = {}

    for index, chunk in enumerate(common.chunked_list(video_id_list, PATH_REQUEST_SIZE_STD)):
        if index >= perpetual_range_start:
            if number_of_requests == 0:
                if len(video_id_list) > count:
                    # Exists others elements
                    perpetual_range_selector['_perpetual_range_selector'] = {'next_start': perpetual_range_start + 1}
                break
            chunked_video_list.append(chunk)
            number_of_requests -= 1
        count += len(chunk)

    if perpetual_range_start > 0:
        previous_start = perpetual_range_start - 1
        if '_perpetual_range_selector' in perpetual_range_selector:
            perpetual_range_selector['_perpetual_range_selector']['previous_start'] = previous_start
        else:
            perpetual_range_selector['_perpetual_range_selector'] = {'previous_start': previous_start}
    return chunked_video_list, perpetual_range_selector


def delay_anti_ban():
    """Adds some random delay between operations to limit servers load and ban risks"""
    # Not so reliable workaround NF has strict control over the number/type of requests in a short space of time
    # More than 100~ of requests could still cause HTTP errors by blocking requests to the server
    xbmc.sleep(random.randint(1000, 4001))
