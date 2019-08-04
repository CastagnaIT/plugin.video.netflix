# -*- coding: utf-8 -*-
"""Navigation handler for actions"""
from __future__ import unicode_literals

import xbmc

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.ui as ui


class AddonActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing AddonActionExecutor: {}'
                     .format(params))
        self.params = params

    def logout(self, pathitems=None):
        """Perform account logout"""
        # pylint: disable=unused-argument
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

    def toggle_adult_pin(self, pathitems=None):
        """Toggle adult PIN verification"""
        # pylint: disable=no-member, unused-argument
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
            ui.show_notification(common.get_local_string(30180))

    @common.time_execution(immediate=False)
    def purge_cache(self, pathitems=None):
        """Clear the cache. If on_disk param is supplied, also clear cached
        items from disk"""
        # pylint: disable=unused-argument
        g.CACHE.invalidate(self.params.get('on_disk', False))
        if self.params.get('on_disk', False):
            common.delete_file('resources.lib.services.playback.stream_continuity.ndb')
        if not self.params.get('no_notification', False):
            ui.show_notification(common.get_local_string(30135))


def _sync_library(videoid, operation):
    operation = {
        'add': 'export_silent',
        'remove': 'remove_silent'}.get(operation)
    if operation and g.ADDON.getSettingBool('mylist_library_sync'):
        common.debug('Syncing library due to change of my list')
        # We need to wait a little before syncing the library to prevent race
        # conditions with the Container refresh
        common.schedule_builtin(
            '00:03',
            common.run_plugin_action(
                common.build_url([operation], videoid, mode=g.MODE_LIBRARY)),
            name='NetflixLibrarySync')
