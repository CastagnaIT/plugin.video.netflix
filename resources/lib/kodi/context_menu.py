# -*- coding: utf-8 -*-
"""Helper functions to generating context menu items"""
from __future__ import unicode_literals

from resources.lib.globals import g
import resources.lib.common as common
import resources.lib.api.shakti as api
import resources.lib.kodi.library as library


def ctx_item_url(paths, mode=g.MODE_ACTION):
    """Return a function that builds an URL from a videoid
    for the predefined path"""
    def ctx_url_builder(videoid):
        """Build a context menu item URL"""
        return common.build_url(paths, videoid, mode=mode)
    return ctx_url_builder


CONTEXT_MENU_ACTIONS = {
    'export': {
        'label': common.get_local_string(30018),
        'url': ctx_item_url(['export'], g.MODE_LIBRARY)},
    'remove': {
        'label': common.get_local_string(30030),
        'url': ctx_item_url(['remove'], g.MODE_LIBRARY)},
    'update': {
        'label': common.get_local_string(30061),
        'url': ctx_item_url(['update'], g.MODE_LIBRARY)},
    'rate': {
        'label': common.get_local_string(30019),
        'url': ctx_item_url(['rate'])},
    'add_to_list': {
        'label': common.get_local_string(30021),
        'url': ctx_item_url(['my_list', 'add'])},
    'remove_from_list': {
        'label': common.get_local_string(30020),
        'url': ctx_item_url(['my_list', 'remove'])},
}


def generate_context_menu_items(videoid):
    """Generate context menu items for a listitem"""
    items = _generate_library_ctx_items(videoid)

    if videoid.mediatype != common.VideoId.SEASON:
        items.insert(0, _ctx_item('rate', videoid))

    if videoid.mediatype in [common.VideoId.MOVIE, common.VideoId.SHOW]\
        and g.PERSISTENT_STORAGE.get('profile_have_mylist_menu', False):
        list_action = ('remove_from_list'
                       if videoid.value in api.mylist_items()
                       else 'add_to_list')
        items.insert(0, _ctx_item(list_action, videoid))

    return items


def _generate_library_ctx_items(videoid):
    library_actions = (['remove', 'update']
                       if library.is_in_library(videoid)
                       else ['export'])
    return [_ctx_item(action, videoid) for action in library_actions]


def _ctx_item(template, videoid):
    """Create a context menu item based on the given template and videoid"""
    return (CONTEXT_MENU_ACTIONS[template]['label'],
            common.run_plugin_action(
                CONTEXT_MENU_ACTIONS[template]['url'](videoid)))
