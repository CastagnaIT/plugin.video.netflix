# -*- coding: utf-8 -*-
"""Navigation handler for actions"""
from __future__ import absolute_import, division, unicode_literals

import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.ui as ui


class AddonActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing AddonActionExecutor: {}', params)
        self.params = params

    def logout(self, pathitems=None):  # pylint: disable=unused-argument
        """Perform account logout"""
        api.logout()

    def save_autologin(self, pathitems):
        """Save autologin data"""
        try:
            g.settings_monitor_suspended(True)
            g.ADDON.setSetting('autologin_user',
                               self.params['autologin_user'])
            g.ADDON.setSetting('autologin_id', pathitems[1])
            g.ADDON.setSetting('autologin_enable', 'true')
            g.settings_monitor_suspended(False)
        except (KeyError, IndexError):
            common.error('Cannot save autologin - invalid params')
        g.CACHE.invalidate()
        common.refresh_container()

    def toggle_adult_pin(self, pathitems=None):  # pylint: disable=no-member, unused-argument
        """Toggle adult PIN verification"""
        pin = ui.ask_for_pin()
        if pin is None:
            return
        if api.verify_pin(pin):
            current_setting = {'true': True, 'false': False}.get(
                g.ADDON.getSetting('adultpin_enable').lower())
            g.settings_monitor_suspended(True)
            g.ADDON.setSetting('adultpin_enable', str(not current_setting))
            g.settings_monitor_suspended(False)
            g.flush_settings()
            ui.show_notification(
                common.get_local_string(30107 if current_setting else 30108))
        else:
            ui.show_notification(common.get_local_string(30106))

    @common.inject_video_id(path_offset=1)
    @common.time_execution(immediate=False)
    def rate(self, videoid):
        """Rate an item on Netflix. Ask for a rating if there is none supplied
        in the path."""
        rating = self.params.get('rating') or ui.ask_for_rating()
        if rating is not None:
            api.rate(videoid, rating)

    @common.inject_video_id(path_offset=2, inject_remaining_pathitems=True)
    @common.time_execution(immediate=False)
    def my_list(self, videoid, pathitems):
        """Add or remove an item from my list"""
        operation = pathitems[1]
        api.update_my_list(videoid, operation)
        _sync_library(videoid, operation)
        common.refresh_container()

    @common.inject_video_id(path_offset=1)
    @common.time_execution(immediate=False)
    def trailer(self, videoid):
        """Get the trailer list"""
        video_list = api.supplemental_video_list(videoid, 'trailers')
        if video_list.videos:
            url = common.build_url(['supplemental', videoid.value, videoid.mediatype, 'trailers'],
                                   mode=g.MODE_DIRECTORY)
            xbmc.executebuiltin('Container.Update({})'.format(url))
        else:
            ui.show_notification(common.get_local_string(30111))

    @common.time_execution(immediate=False)
    def purge_cache(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache. If on_disk param is supplied, also clear cached
        items from disk"""
        g.CACHE.invalidate(self.params.get('on_disk', False))
        if self.params.get('on_disk', False):
            common.delete_file('resources.lib.services.playback.stream_continuity.ndb')
        if not self.params.get('no_notification', False):
            ui.show_notification(common.get_local_string(30135))

    def force_update_mylist(self, pathitems=None):  # pylint: disable=unused-argument
        """Clear the cache of my list to force the update"""
        from resources.lib.cache import CACHE_COMMON
        g.CACHE.invalidate_entry(CACHE_COMMON, 'mylist')
        g.CACHE.invalidate_entry(CACHE_COMMON, 'my_list_items')

    def view_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Show the ESN in use"""
        ui.show_ok_dialog(common.get_local_string(30016), g.get_esn())

    def reset_esn(self, pathitems=None):  # pylint: disable=unused-argument
        """Reset the ESN stored (retrieved from website and manual)"""
        from resources.lib.database.db_utils import (TABLE_SESSION, TABLE_SETTINGS_MONITOR)
        if not ui.ask_for_confirmation(common.get_local_string(30217),
                                       common.get_local_string(30218)):
            return
        g.settings_monitor_suspended(True)
        # Reset the ESN obtained from website/generated
        g.LOCAL_DB.set_value('esn', '', TABLE_SESSION)
        # Reset the custom ESN (manual ESN from settings)
        g.ADDON.setSetting('esn', '')
        # Reset the custom ESN (backup of manual ESN from settings, used in settings_monitor.py)
        g.LOCAL_DB.set_value('custom_esn', '', TABLE_SETTINGS_MONITOR)
        g.settings_monitor_suspended(False)
        # Perform a new login to get/generate a new ESN
        api.login(ask_credentials=False)
        # Warning after login netflix switch to the main profile! so return to the main screen
        url = 'plugin://plugin.video.netflix/directory/root'
        xbmc.executebuiltin('XBMC.Container.Update(path,replace)')  # Clean path history
        xbmc.executebuiltin('Container.Update({})'.format(url))  # Open root page


def _sync_library(videoid, operation):
    operation = {
        'add': 'export_silent',
        'remove': 'remove_silent'}.get(operation)
    if operation and g.ADDON.getSettingBool('lib_sync_mylist'):
        sync_mylist_profile_guid = g.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                         g.LOCAL_DB.get_guid_owner_profile())
        # Allow to sync library with My List only by chosen profile
        if sync_mylist_profile_guid != g.LOCAL_DB.get_active_profile_guid():
            return
        common.debug('Syncing library due to change of my list')
        # xbmc.executebuiltin is running with Block, to prevent update the list before op. is done
        common.run_plugin(common.build_url([operation], videoid, mode=g.MODE_LIBRARY), block=True)
