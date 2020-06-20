# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Stateful Netflix session management: initialize the netflix session

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

from functools import wraps

import resources.lib.common as common
from resources.lib.globals import g
from resources.lib.database.db_utils import (TABLE_SESSION)
from resources.lib.api.exceptions import (NotLoggedInError, NotConnected)


def needs_login(func):
    """
    Decorator to ensure that a valid login is present when calling a method
    """
    # pylint: disable=protected-access, missing-docstring
    @wraps(func)
    def ensure_login(*args, **kwargs):
        session = args[0]
        # I make sure that the connection is present..
        if not common.is_internet_connected():
            raise NotConnected('Internet connection not available')
        # ..this check verifies only if locally there are the data to correctly perform the login
        if not session.is_logged_in():
            raise NotLoggedInError
        return func(*args, **kwargs)
    return ensure_login


class NFSessionBase(object):
    """Initialize the netflix session"""

    slots = None
    """Slots to be registered with AddonSignals. Is set in _register_slots"""

    session = None
    """The requests.session object to handle communication to Netflix"""

    verify_ssl = True
    """Use SSL verification when performing requests"""

    def __init__(self):
        self.verify_ssl = bool(g.ADDON.getSettingBool('ssl_verification'))
        self.is_prefetch_login = False
        self._init_session()

    @common.time_execution(immediate=True)
    def _init_session(self):
        """Initialize the session to use for all future connections"""
        try:
            self.session.close()
            common.info('Session closed')
        except AttributeError:
            pass
        from requests import session
        self.session = session()
        self.session.headers.update({
            'User-Agent': common.get_user_agent(enable_android_mediaflag_fix=True),
            'Accept-Encoding': 'gzip, deflate, br'
        })
        common.info('Initialized new session')

    @property
    def account_hash(self):
        """The unique hash of the current account"""
        from base64 import urlsafe_b64encode
        return urlsafe_b64encode(
            common.get_credentials().get('email', 'NoMail').encode('utf-8')).decode('utf-8')

    @property
    def auth_url(self):
        """Return authentication url"""
        return g.LOCAL_DB.get_value('auth_url', table=TABLE_SESSION)

    @auth_url.setter
    def auth_url(self, value):
        g.LOCAL_DB.set_value('auth_url', value, TABLE_SESSION)
