# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Stateful Netflix session management

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import resources.lib.common as common
from resources.lib.globals import G
from resources.lib.services.nfsession.directorybuilder.dir_builder import DirectoryBuilder
from resources.lib.services.nfsession.msl.msl_handler import MSLHandler
from resources.lib.services.nfsession.nfsession_ops import NFSessionOperations
from resources.lib.services.playback.action_controller import ActionController
from resources.lib.utils.logging import LOG


class NetflixSession:
    """Stateful netflix session management"""

    http_ipc_slots = {}

    def __init__(self):
        # Create and establish the Netflix session
        self.nfsession = NFSessionOperations()
        # Create MSL handler
        self.msl_handler = MSLHandler(self.nfsession)
        # Set to the nfsession the reference to the current MSL Handler object
        self.nfsession.msl_handler = self.msl_handler
        # Initialize correlated features
        self.directory_builder = DirectoryBuilder(self.nfsession)
        self.action_controller = ActionController(self.nfsession, self.msl_handler, self.directory_builder)
        # Register the functions to IPC
        slots = (self.nfsession.slots + self.msl_handler.slots +
                 self.directory_builder.slots + [self.library_auto_update])
        for slot in slots:
            func_name = slot.__name__
            # For HTTP IPC (http_server.py)
            self.http_ipc_slots[func_name] = slot
            # For AddonSignals IPC
            common.register_slot(slot, func_name)

    def library_auto_update(self):
        """Run the library auto update"""
        try:
            # Call the function in a thread to return immediately without blocking the service
            common.run_threaded(True, self._run_library_auto_update)
        except Exception as exc:  # pylint: disable=broad-except
            LOG.error('library_auto_update raised an error: {}', exc)

    def _run_library_auto_update(self):
        from resources.lib.kodi.library import Library
        library_cls = Library(self.nfsession.get_metadata,
                              self.directory_builder.get_mylist_videoids_profile_switch,
                              self.directory_builder.req_profiles_info)
        library_cls.auto_update_library(G.ADDON.getSettingBool('lib_sync_mylist'),
                                        show_prg_dialog=False,
                                        update_profiles=True)
