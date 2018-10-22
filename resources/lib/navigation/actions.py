# -*- coding: utf-8 -*-
"""Navigation handler for actions"""
from __future__ import unicode_literals

import xbmc
from xbmcaddon import Addon

import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.api.shakti as api
from resources.lib.navigation import InvalidPathError

def execute(pathitems, params):
    """Execute an action as specified by the path"""
    try:
        executor = ActionExecutor(params).__getattribute__(pathitems[0])
    except (AttributeError, IndexError):
        raise InvalidPathError('Unknown action {}'.format('/'.join(pathitems)))

    common.debug('Invoking action executor {}'.format(executor.__name__))

    if len(pathitems) > 1:
        executor((pathitems[1:]))
    else:
        executor()

class ActionExecutor(object):
    """Executes actions"""
    # pylint: disable=no-self-use
    def __init__(self, params):
        common.debug('Initializing action executor: {}'.format(params))
        self.params = params

    def logout(self):
        """Perform account logout"""
        api.logout()

    def opensettings(self, pathitems):
        """Open settings of another addon"""
        try:
            Addon(pathitems[1]).openSettings()
        except IndexError:
            raise InvalidPathError('Missing target addon id')

    def save_autologin(self, pathitems):
        """Save autologin data"""
        try:
            common.ADDON.setSetting('autologin_user',
                                    self.params['autologin_user'])
            common.ADDON.setSetting('autologin_id', pathitems[0])
            common.ADDON.setSetting('autologin_enable', 'true')
        except (KeyError, IndexError):
            common.error('Cannot save autologin - invalid params')
        cache.invalidate_cache()
        xbmc.executebuiltin('Container.Refresh')

    def switch_account(self):
        """Logo out of the curent account and login into another one"""
        api.logout()
        api.login()

    def toggle_adult_pin(self):
        """Toggle adult PIN verification"""
        # pylint: disable=no-member
        common.ADDON.setSettingBool(
            not common.ADDON.getSettingBool('adultpin_enable'))

    def rate(self, pathitems):
        """Rate an item on Netflix. Ask for a rating if there is none supplied
        in the path."""
        if len(pathitems) < 2:
            rating = ui.ask_for_rating()
        else:
            rating = pathitems[1]
        api.rate(pathitems[0], rating)

    def my_list(self, pathitems):
        """Add or remove an item from my list"""
        if len(pathitems) < 2:
            raise InvalidPathError('Missing video id')

        if pathitems[0] == 'add':
            api.add_to_list(pathitems[1])
        elif pathitems[0] == 'remove':
            api.remove_from_list(pathitems[1])
        else:
            raise InvalidPathError('Unknown my-list action: {}'
                                   .format(pathitems[0]))
        xbmc.executebuiltin('Container.Refresh')
