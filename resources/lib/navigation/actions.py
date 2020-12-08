# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Navigation handler for actions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import xbmc

import resources.lib.common as common
import resources.lib.kodi.ui as ui
import resources.lib.utils.api_requests as api
from resources.lib.common import cache_utils
from resources.lib.common.exceptions import MissingCredentialsError, CacheMiss
from resources.lib.database.db_utils import (TABLE_SESSION, TABLE_SETTINGS_MONITOR)
from resources.lib.globals import G
from resources.lib.kodi.library import get_library_cls
from resources.lib.utils.api_paths import VIDEO_LIST_RATING_THUMB_PATHS, SUPPLEMENTAL_TYPE_TRAILERS
from resources.lib.utils.esn import get_esn, generate_android_esn, generate_esn
from resources.lib.utils.logging import LOG, measure_exec_time_decorator


class AddonActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        LOG.debug('Initializing "AddonActionExecutor" with params: {}', params)
        self.params = params

    def logout(self, pathitems=None):  # pylint: disable=unused-argument
        """Perform account logout"""
        api.logout()

    def autoselect_set_profile(self, pathitems):  # pylint: disable=unused-argument
        """Save the GUID for profile auto-selection"""
        G.LOCAL_DB.set_value('autoselect_profile_guid', self.params['profile_guid'])
        profile_name = G.LOCAL_DB.get_profile_config('profileName', '???', self.params['profile_guid'])
        common.container_refresh()
        ui.show_notification(profile_name, title=common.get_local_string(30055))

    def autoselect_remove_profile(self, pathitems):  # pylint: disable=unused-argument
        """Remove the GUID from auto-selection"""
        G.LOCAL_DB.set_value('autoselect_profile_guid', '')
        profile_name = G.LOCAL_DB.get_profile_config('profileName', '???', self.params['profile_guid'])
        common.container_refresh()
        ui.show_notification(profile_name, title=common.get_local_string(30056))

    def library_playback_set_profile(self, pathitems=None):  # pylint: disable=unused-argument
        """Save the GUID for the playback from Kodi library"""
        G.LOCAL_DB.set_value('library_playback_profile_guid', self.params['profile_guid'])
        profile_name = G.LOCAL_DB.get_profile_config('profileName', '???', self.params['profile_guid'])
        common.container_refresh()
        ui.show_notification(profile_name, title=common.get_local_string(30052))

    def library_playback_remove_profile(self, pathitems):  # pylint: disable=unused-argument
        """Remove the GUID for the playback from Kodi library"""
        G.LOCAL_DB.set_value('library_playback_profile_guid', '')
        profile_name = G.LOCAL_DB.get_profile_config('profileName', '???', self.params['profile_guid'])
        common.container_refresh()
        ui.show_notification(profile_name, title=common.get_local_string(30053))

    def parental_control(self, pathitems=None):  # pylint: disable=unused-argument
        """Open parental control settings dialog"""
        password = ui.ask_for_password()
        if not password:
            return
        try:
            parental_control_data = api.get_parental_control_data(self.params['profile_guid'],
                                                                  password)
            ui.show_modal_dialog(False,
                                 ui.xmldialogs.ParentalControl,
                                 'plugin-video-netflix-ParentalControl.xml',
                                 G.ADDON.getAddonInfo('path'),
                                 **parental_control_data)
        except MissingCredentialsError:
            ui.show_ok_dialog('Netflix', common.get_local_string(30009))

    @common.inject_video_id(path_offset=1)
    @measure_exec_time_decorator()
    def rate_thumb(self, videoid):
        """Rate an item on Netflix. Ask for a thumb rating"""
        # Get updated user rating info for this videoid
        raw_data = api.get_video_raw_data([videoid], VIDEO_LIST_RATING_THUMB_PATHS)
        if raw_data.get('videos', {}).get(videoid.value):
            video_data = raw_data['videos'][videoid.value]
            title = video_data.get('title')
            track_id_jaw = video_data.get('trackIds', {})['trackId_jaw']
            is_thumb_rating = video_data.get('userRating', {}).get('type', '') == 'thumb'
            user_rating = video_data.get('userRating', {}).get('userRating') if is_thumb_rating else None
            ui.show_modal_dialog(False,
                                 ui.xmldialogs.RatingThumb,
                                 'plugin-video-netflix-RatingThumb.xml',
                                 G.ADDON.getAddonInfo('path'),
                                 videoid=videoid,
                                 title=title,
                                 track_id_jaw=track_id_jaw,
                                 user_rating=user_rating)
        else:
            LOG.warn('Rating thumb video list api request no got results for {}', videoid)

    # Old rating system
    # @common.inject_video_id(path_offset=1)
    # @common.time_execution(immediate=False)
    # def rate(self, videoid):
    #     """Rate an item on Netflix. Ask for a rating if there is none supplied
    #     in the path."""
    #     rating = self.params.get('rating') or ui.ask_for_rating()
    #     if rating is not None:
    #         api.rate(videoid, rating)

    @common.inject_video_id(path_offset=2, inject_remaining_pathitems=True)
    @measure_exec_time_decorator()
    def my_list(self, videoid, pathitems):
        """Add or remove an item from my list"""
        operation = pathitems[1]
        api.update_my_list(videoid, operation, self.params)
        sync_library(videoid, operation)
        common.container_refresh()

    @common.inject_video_id(path_offset=1)
    @measure_exec_time_decorator()
    def trailer(self, videoid):
        """Get the trailer list"""
        from json import dumps
        menu_data = {'path': ['is_context_menu_item', 'is_context_menu_item'],  # Menu item do not exists
                     'title': common.get_local_string(30179)}
        video_id_dict = videoid.to_dict()
        list_data, extra_data = common.make_call('get_video_list_supplemental',  # pylint: disable=unused-variable
                                                 {
                                                     'menu_data': menu_data,
                                                     'video_id_dict': video_id_dict,
                                                     'supplemental_type': SUPPLEMENTAL_TYPE_TRAILERS
                                                 })
        if list_data:
            url = common.build_url(['supplemental'],
                                   params={'video_id_dict': dumps(video_id_dict),
                                           'supplemental_type': SUPPLEMENTAL_TYPE_TRAILERS},
                                   mode=G.MODE_DIRECTORY)
            common.container_update(url)
        else:
            ui.show_notification(common.get_local_string(30111))

    @measure_exec_time_decorator()
    def purge_cache(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache. If on_disk param is supplied, also clear cached items from disk"""
        G.CACHE.clear(clear_database=self.params.get('on_disk', False))
        ui.show_notification(common.get_local_string(30135))

    def force_update_list(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache of my list to force the update"""
        if self.params['menu_id'] == 'myList':
            G.CACHE.clear([cache_utils.CACHE_MYLIST], clear_database=False)
        if self.params['menu_id'] == 'continueWatching':
            # Delete the cache of continueWatching list
            # pylint: disable=unused-variable
            is_exists, list_id = common.make_call('get_continuewatching_videoid_exists', {'video_id': ''})
            if list_id:
                G.CACHE.delete(cache_utils.CACHE_COMMON, list_id, including_suffixes=True)
            # When the continueWatching context is invalidated from a refreshListByContext call
            # the LoCo need to be updated to obtain the new list id, so we delete the cache to get new data
            G.CACHE.delete(cache_utils.CACHE_COMMON, 'loco_list')

    def view_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Show the ESN in use"""
        ui.show_ok_dialog(common.get_local_string(30016), get_esn())

    def reset_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Reset the ESN stored (retrieved from website and manual)"""
        if not ui.ask_for_confirmation(common.get_local_string(30217),
                                       common.get_local_string(30218)):
            return
        # Generate a new ESN
        generated_esn = self._get_new_esn()
        # Reset the ESN obtained from website/generated
        G.LOCAL_DB.set_value('esn', '', TABLE_SESSION)
        # Reset the custom ESN (manual ESN from settings)
        G.settings_monitor_suspend(at_first_change=True)
        G.ADDON.setSetting('esn', '')
        # Reset the custom ESN (backup of manual ESN from settings, used in settings_monitor.py)
        G.LOCAL_DB.set_value('custom_esn', '', TABLE_SETTINGS_MONITOR)
        # Save the new ESN
        G.LOCAL_DB.set_value('esn', generated_esn, TABLE_SESSION)
        # Reinitialize the MSL handler (delete msl data file, then reset everything)
        common.send_signal(signal=common.Signals.REINITIALIZE_MSL_HANDLER, data=True)
        # Show login notification
        ui.show_notification(common.get_local_string(30109))
        # Open root page
        common.container_update(G.BASE_URL, True)

    def _get_new_esn(self):
        if common.get_system_platform() == 'android':
            return generate_android_esn()
        # In the all other systems, create a new ESN by using the existing ESN prefix
        current_esn = G.LOCAL_DB.get_value('esn', table=TABLE_SESSION)
        from re import search
        esn_prefix_match = search(r'.+-', current_esn)
        if not esn_prefix_match:
            raise Exception('It was not possible to generate a new ESN. Before try login.')
        return generate_esn(esn_prefix_match.group(0))

    @common.inject_video_id(path_offset=1)
    def change_watched_status(self, videoid):
        """Change the watched status of a video, only when sync of watched status with NF is enabled"""
        change_watched_status_locally(videoid)

    def configuration_wizard(self, pathitems=None):  # pylint: disable=unused-argument
        """Run the add-on configuration wizard"""
        from resources.lib.config_wizard import run_addon_configuration
        run_addon_configuration(show_end_msg=True)

    @common.inject_video_id(path_offset=1)
    def remove_watched_status(self, videoid):
        """Remove the watched status from the Netflix service"""
        if not ui.ask_for_confirmation(common.get_local_string(30168),
                                       common.get_local_string(30300).format(xbmc.getInfoLabel('ListItem.Label'))):
            return
        if not api.remove_watched_status(videoid):
            ui.show_notification('The operation was cancelled due to an unexpected error')
            return
        # Check if item is in the cache
        videoid_exists, list_id = common.make_http_call('get_continuewatching_videoid_exists',
                                                        {'video_id': str(videoid.value)})
        if videoid_exists:
            # Try to remove the videoid from the list in the cache
            try:
                video_list_sorted_data = G.CACHE.get(cache_utils.CACHE_COMMON, list_id)
                del video_list_sorted_data.videos[videoid.value]
                G.CACHE.add(cache_utils.CACHE_COMMON, list_id, video_list_sorted_data)
                common.json_rpc('Input.Down')  # Avoids selection back to the top
            except CacheMiss:
                pass
        common.container_refresh()

    def show_availability_message(self, pathitems=None):  # pylint: disable=unused-argument
        """Show a message to the user to show the date of availability of a video"""
        ui.show_ok_dialog(xbmc.getInfoLabel('ListItem.Label'),
                          xbmc.getInfoLabel('ListItem.Property(nf_availability_message)'))

def sync_library(videoid, operation):
    if operation and G.ADDON.getSettingBool('lib_sync_mylist') and G.ADDON.getSettingInt('lib_auto_upd_mode') == 2:
        sync_mylist_profile_guid = G.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                         G.LOCAL_DB.get_guid_owner_profile())
        # Allow to sync library with My List only by chosen profile
        if sync_mylist_profile_guid != G.LOCAL_DB.get_active_profile_guid():
            return
        LOG.debug('Syncing library due to change of My list')
        if operation == 'add':
            get_library_cls().export_to_library(videoid, False)
        elif operation == 'remove':
            get_library_cls().remove_from_library(videoid, False)


def change_watched_status_locally(videoid):
    """Change the watched status locally"""
    # Todo: how get resumetime/playcount of selected item for calculate current watched status?
    profile_guid = G.LOCAL_DB.get_active_profile_guid()
    current_value = G.SHARED_DB.get_watched_status(profile_guid, videoid.value, None, bool)
    if current_value:
        txt_index = 1
        G.SHARED_DB.set_watched_status(profile_guid, videoid.value, False)
    elif current_value is not None and not current_value:
        txt_index = 2
        G.SHARED_DB.delete_watched_status(profile_guid, videoid.value)
    else:
        txt_index = 0
        G.SHARED_DB.set_watched_status(profile_guid, videoid.value, True)
    ui.show_notification(common.get_local_string(30237).split('|')[txt_index])
    common.container_refresh()
