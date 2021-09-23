# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2020 Stefano Gottardo (original implementation module)
    Navigation for search menu

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from copy import deepcopy

import xbmcgui
import xbmcplugin

import resources.lib.utils.api_requests as api
from resources.lib import common
from resources.lib.globals import G
from resources.lib.kodi import ui
from resources.lib.kodi.context_menu import generate_context_menu_searchitem
from resources.lib.navigation.directory_utils import (finalize_directory, end_of_directory,
                                                      custom_viewmode, get_title)
from resources.lib.utils.logging import LOG, measure_exec_time_decorator

# The search types allows you to provide a modular structure to the search feature,
# in this way you can add new/remove types of search in a simple way.
# To add a new type: add the new type name to SEARCH_TYPES, then implement the new type to search_add/search_query.


SEARCH_TYPES = ['text', 'audio_lang', 'subtitles_lang', 'genre_id']
SEARCH_TYPES_DESC = {
    'text': common.get_local_string(30410),
    'audio_lang': common.get_local_string(30411),
    'subtitles_lang': common.get_local_string(30412),
    'genre_id': common.get_local_string(30413)
}


def route_search_nav(pathitems, perpetual_range_start, dir_update_listing, params):
    if 'query' in params:
        path = 'query'
    else:
        path = pathitems[2] if len(pathitems) > 2 else 'list'
    LOG.debug('Routing "search" navigation to: {}', path)
    ret = True
    if path == 'list':
        search_list()
    elif path == 'add':
        ret = search_add()
    elif path == 'edit':
        search_edit(params['row_id'])
    elif path == 'remove':
        search_remove(params['row_id'])
    elif path == 'clear':
        ret = search_clear()
    elif path == 'query':
        # Used to make a search by text from a JSON-RPC request
        # without save the item to the add-on database
        # Endpoint: plugin://plugin.video.netflix/directory/search/search/?query=something
        ret = exec_query(None, 'text', None, params['query'], perpetual_range_start, dir_update_listing,
                         {'query': params['query']})
    else:
        ret = search_query(path, perpetual_range_start, dir_update_listing)
    if not ret:
        xbmcplugin.endOfDirectory(G.PLUGIN_HANDLE, succeeded=False)


def search_list(dir_update_listing=False):
    """Show the list of search item (main directory)"""
    dir_items = [_create_diritem_from_row(row) for row in G.LOCAL_DB.get_search_list()]
    dir_items.insert(0, _get_diritem_add())
    dir_items.append(_get_diritem_clear())
    sort_type = 'sort_nothing'
    if G.ADDON.getSettingInt('menu_sortorder_search_history') == 1:
        sort_type = 'sort_label_ignore_folders'
    finalize_directory(dir_items, G.CONTENT_FOLDER, sort_type,
                       common.get_local_string(30400))
    end_of_directory(dir_update_listing)


def search_add():
    """Perform actions to add and execute a new research"""
    # Ask to user the type of research
    search_types_desc = [SEARCH_TYPES_DESC.get(stype, 'Unknown') for stype in SEARCH_TYPES]
    type_index = ui.show_dlg_select(common.get_local_string(30401), search_types_desc)
    if type_index == -1:  # Cancelled
        return False
    # If needed ask to user other info, then save the research to the database
    search_type = SEARCH_TYPES[type_index]
    row_id = None
    if search_type == 'text':
        search_term = ui.ask_for_search_term()
        if search_term and search_term.strip():
            row_id = G.LOCAL_DB.insert_search_item(SEARCH_TYPES[type_index], search_term.strip())
    elif search_type == 'audio_lang':
        row_id = _search_add_bylang(SEARCH_TYPES[type_index], api.get_available_audio_languages())
    elif search_type == 'subtitles_lang':
        row_id = _search_add_bylang(SEARCH_TYPES[type_index], api.get_available_subtitles_languages())
    elif search_type == 'genre_id':
        genre_id = ui.show_dlg_input_numeric(search_types_desc[type_index], mask_input=False)
        if genre_id:
            row_id = _search_add_bygenreid(SEARCH_TYPES[type_index], genre_id)
    else:
        raise NotImplementedError(f'Search type index {type_index} not implemented')
    # Redirect to "search" endpoint (otherwise no results in JSON-RPC)
    # Rewrite path history using dir_update_listing + container_update
    # (otherwise will retrigger input dialog on Back or Container.Refresh)
    if row_id is not None and search_query(row_id, 0, False):
        url = common.build_url(['search', 'search', row_id], mode=G.MODE_DIRECTORY, params={'dir_update_listing': True})
        common.container_update(url, False)
        return True
    return False


def _search_add_bylang(search_type, dict_languages):
    search_type_desc = SEARCH_TYPES_DESC.get(search_type, 'Unknown')
    title = f'{search_type_desc} - {common.get_local_string(30405)}'
    index = ui.show_dlg_select(title, list(dict_languages.values()))
    if index == -1:  # Cancelled
        return None
    lang_code = list(dict_languages.keys())[index]
    lang_desc = list(dict_languages.values())[index]
    # In this case the 'value' is used only as title for the ListItem and not for the query
    value = f'{search_type_desc}: {lang_desc}'
    row_id = G.LOCAL_DB.insert_search_item(search_type, value, {'lang_code': lang_code})
    return row_id


def _search_add_bygenreid(search_type, genre_id):
    # If the genre ID exists, the title of the list will be returned
    title = api.get_genre_title(genre_id)
    if not title:
        ui.show_notification(common.get_local_string(30407))
        return None
    # In this case the 'value' is used only as title for the ListItem and not for the query
    title += f' [{genre_id}]'
    row_id = G.LOCAL_DB.insert_search_item(search_type, title, {'genre_id': genre_id})
    return row_id


def search_edit(row_id):
    """Edit a search item"""
    search_item = G.LOCAL_DB.get_search_item(row_id)
    search_type = search_item['Type']
    ret = False
    if search_type == 'text':
        search_term = ui.ask_for_search_term(search_item['Value'])
        if search_term and search_term.strip():
            G.LOCAL_DB.update_search_item_value(row_id, search_term.strip())
            ret = True
    if not ret:
        return
    common.container_update(common.build_url(['search', 'search', row_id], mode=G.MODE_DIRECTORY))


def search_remove(row_id):
    """Remove a search item"""
    LOG.debug('Removing search item with ID {}', row_id)
    G.LOCAL_DB.delete_search_item(row_id)
    common.json_rpc('Input.Down')  # Avoids selection back to the top
    common.container_refresh()


def search_clear():
    """Clear all search items"""
    if not ui.ask_for_confirmation(common.get_local_string(30404), common.get_local_string(30406)):
        return False
    G.LOCAL_DB.clear_search_items()
    common.container_refresh()
    return True


@measure_exec_time_decorator()
def search_query(row_id, perpetual_range_start, dir_update_listing):
    """Perform the research"""
    # Get item from database
    search_item = G.LOCAL_DB.get_search_item(row_id)
    if not search_item:
        ui.show_error_info('Search error', 'Item not found in the database.')
        return False
    # Update the last access data (move on top last used items)
    if not perpetual_range_start:
        G.LOCAL_DB.update_search_item_last_access(row_id)
    return exec_query(row_id, search_item['Type'], search_item['Parameters'], search_item['Value'],
                      perpetual_range_start, dir_update_listing)


def exec_query(row_id, search_type, search_params, search_value, perpetual_range_start, dir_update_listing,
               path_params=None):
    menu_data = deepcopy(G.MAIN_MENU_ITEMS['search'])
    if search_type == 'text':
        call_args = {
            'menu_data': menu_data,
            'search_term': search_value,
            'pathitems': ['search', 'search', row_id] if row_id else ['search', 'search'],
            'path_params': path_params,
            'perpetual_range_start': perpetual_range_start
        }
        dir_items, extra_data = common.make_call('get_video_list_search', call_args)
    elif search_type == 'audio_lang':
        menu_data['query_without_reference'] = True
        call_args = {
            'menu_data': menu_data,
            'pathitems': ['search', 'search', row_id],
            'perpetual_range_start': perpetual_range_start,
            'context_name': 'spokenAudio',
            'context_id': common.convert_from_string(search_params, dict)['lang_code']
        }
        dir_items, extra_data = common.make_call('get_video_list_sorted_sp', call_args)
    elif search_type == 'subtitles_lang':
        menu_data['query_without_reference'] = True
        call_args = {
            'menu_data': menu_data,
            'pathitems': ['search', 'search', row_id],
            'perpetual_range_start': perpetual_range_start,
            'context_name': 'subtitles',
            'context_id': common.convert_from_string(search_params, dict)['lang_code']
        }
        dir_items, extra_data = common.make_call('get_video_list_sorted_sp', call_args)
    elif search_type == 'genre_id':
        call_args = {
            'menu_data': menu_data,
            'pathitems': ['search', 'search', row_id],
            'perpetual_range_start': perpetual_range_start,
            'context_name': 'genres',
            'context_id': common.convert_from_string(search_params, dict)['genre_id']
        }
        dir_items, extra_data = common.make_call('get_video_list_sorted_sp', call_args)
    else:
        raise NotImplementedError(f'Search type {search_type} not implemented')
    # Show the results
    if not dir_items:
        ui.show_notification(common.get_local_string(30407))
        return False
    _search_results_directory(search_value, menu_data, dir_items, extra_data, dir_update_listing)
    return True


@custom_viewmode(G.VIEW_SHOW)
def _search_results_directory(search_value, menu_data, dir_items, extra_data, dir_update_listing):
    extra_data['title'] = f'{common.get_local_string(30400)} - {search_value}'
    finalize_directory(dir_items, menu_data.get('content_type', G.CONTENT_SHOW),
                       title=get_title(menu_data, extra_data))
    end_of_directory(dir_update_listing)
    return menu_data.get('view')


def _get_diritem_add():
    """Generate the "add" menu item"""
    list_item = xbmcgui.ListItem(label=common.get_local_string(30403), offscreen=True)
    list_item.setArt({'icon': 'DefaultAddSource.png'})
    list_item.setProperty('specialsort', 'top')  # Force an item to stay on top
    return common.build_url(['search', 'search', 'add'], mode=G.MODE_DIRECTORY), list_item, True


def _get_diritem_clear():
    """Generate the "clear" menu item"""
    list_item = xbmcgui.ListItem(label=common.get_local_string(30404), offscreen=True)
    list_item.setArt({'icon': 'icons\\infodialogs\\uninstall.png'})
    list_item.setProperty('specialsort', 'bottom')  # Force an item to stay on bottom
    # This ListItem is not set as folder so that the executed command is not added to the history
    return common.build_url(['search', 'search', 'clear'], mode=G.MODE_DIRECTORY), list_item, False


def _create_diritem_from_row(row):
    row_id = str(row['ID'])
    search_desc = common.get_local_string(30401) + ': ' + SEARCH_TYPES_DESC.get(row['Type'], 'Unknown')
    list_item = xbmcgui.ListItem(label=row['Value'], offscreen=True)
    list_item.setInfo('video', {'plot': search_desc})
    list_item.addContextMenuItems(generate_context_menu_searchitem(row_id, row['Type']))
    return common.build_url(['search', 'search', row_id], mode=G.MODE_DIRECTORY), list_item, True
