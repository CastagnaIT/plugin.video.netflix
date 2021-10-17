# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Initialize the netflix session

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from typing import TYPE_CHECKING

import resources.lib.common as common
from resources.lib.database.db_utils import TABLE_SESSION
from resources.lib.globals import G
from resources.lib.utils.logging import LOG

if TYPE_CHECKING:  # This variable/imports are used only by the editor, so not at runtime
    from resources.lib.services.nfsession.msl.msl_handler import MSLHandler


class SessionBase:
    """Initialize the netflix session"""

    session = None
    """The requests.session object to handle communication to Netflix"""

    # Functions from derived classes to allow perform particular operations in parent classes
    external_func_activate_profile = None  # (set by nfsession_op.py)

    msl_handler: 'MSLHandler' = None
    """A reference to the MSL Handler object"""

    def __init__(self):
        self._init_session()

    def _init_session(self):
        """Initialize the session to use for all future connections"""
        try:
            self.session.close()
            LOG.info('Session closed')
        except AttributeError:
            pass
        import httpx
        # (http1=False, http2=True) means that the client know that server support HTTP/2 and avoid to do negotiations,
        # prior knowledge: https://python-hyper.org/projects/hyper-h2/en/v2.3.1/negotiating-http2.html#prior-knowledge
        self.session = httpx.Client(http1=False, http2=True)
        self.session.max_redirects = 10  # Too much redirects should means some problem
        self.session.headers.update({
            'User-Agent': common.get_user_agent(enable_android_mediaflag_fix=True),
            'Accept-Encoding': 'gzip, deflate, br',
            'Host': 'www.netflix.com'
        })
        LOG.info('Initialized new session')

    @property
    def auth_url(self):
        """Access rights to make HTTP requests on an endpoint"""
        return G.LOCAL_DB.get_value('auth_url', table=TABLE_SESSION)

    @auth_url.setter
    def auth_url(self, value):
        G.LOCAL_DB.set_value('auth_url', value, TABLE_SESSION)
