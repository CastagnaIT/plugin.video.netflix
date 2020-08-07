# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Stateful Netflix session management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from __future__ import absolute_import, division, unicode_literals

import resources.lib.common as common
from resources.lib.globals import G
from resources.lib.services.nfsession.directorybuilder.dir_builder import DirectoryBuilder
from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations


class NetflixSession(object):
    """Stateful netflix session management"""

    http_ipc_slots = {}

    def __init__(self):
        # Create and establish the Netflix session
        self.nfsession = NFSessionOperations()
        # Initialize correlated features
        self.directory_builder = DirectoryBuilder(self.nfsession)
        # Register the functions to IPC
        slots = self.nfsession.slots + self.directory_builder.slots + [self.library_auto_update]
        for slot in slots:
            func_name = slot.__name__
            enveloped_func = common.EnvelopeIPCReturnCall(slot).call
            # For HTTP IPC (http_server.py)
            self.http_ipc_slots[func_name] = enveloped_func
            # For AddonSignals IPC
            common.register_slot(enveloped_func, func_name)

    def library_auto_update(self):
        """Run the library auto update"""
        # Call the function in a thread to return immediately without blocking the service
        common.run_threaded(True, self._run_library_auto_update)

    def _run_library_auto_update(self):
        from resources.lib.kodi.library import Library
        library_cls = Library(self.nfsession.get_metadata,
                              self.directory_builder.get_mylist_videoids_profile_switch,
                              self.directory_builder.req_profiles_info)
        library_cls.auto_update_library(G.ADDON.getSettingBool('lib_sync_mylist'),
                                        show_prg_dialog=False,
                                        update_profiles=True)
