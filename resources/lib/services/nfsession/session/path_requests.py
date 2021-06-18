# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Copyright (C) 2019 Stefano Gottardo - @CastagnaIT
    Manages the PATH requests

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
import json

import resources.lib.utils.api_paths as apipaths
import resources.lib.common as common
from resources.lib.globals import G
from resources.lib.services.nfsession.session.access import SessionAccess
from resources.lib.utils.logging import LOG, measure_exec_time_decorator


class SessionPathRequests(SessionAccess):
    """Manages the PATH requests"""

    @measure_exec_time_decorator(is_immediate=True)
    def path_request(self, paths, use_jsongraph=False):
        """Perform a path request against the Shakti API"""
        LOG.debug('Executing path request: {}', paths)
        custom_params = {}
        if use_jsongraph:
            custom_params['falcor_server'] = '0.1.0'
        # Use separators with dumps because Netflix rejects spaces
        data = 'path=' + '&path='.join(json.dumps(path, separators=(',', ':')) for path in paths)
        response = self.post_safe(
            endpoint='shakti',
            params=custom_params,
            data=data)
        return response['jsonGraph'] if use_jsongraph else response['value']

    @measure_exec_time_decorator(is_immediate=True)
    def perpetual_path_request(self, paths, length_params, perpetual_range_start=None,
                               request_size=apipaths.PATH_REQUEST_SIZE_PAGINATED, no_limit_req=False):
        """
        Perform a perpetual path request against the Shakti API to retrieve a possibly large video list.
        :param paths: The paths that compose the request
        :param length_params: A list of two values, e.g. ['stdlist', [...]]:
                              1: A key of LENGTH_ATTRIBUTES that define where read the total number of objects
                              2: A list of keys used to get the list of objects in the JSON data of received response
        :param perpetual_range_start: defines the starting point of the range of objects to be requested
        :param request_size: defines the size of the range, the total number of objects that will be received
        :param no_limit_req: if True, the perpetual cycle of requests will be 'unlimited'
        :return: Union of all JSON raw data received
        """
        # When the requested video list's size is larger than 'request_size',
        # multiple path requests will be executed with forward shifting range selectors
        # and the results will be combined into one path response.
        response_type, length_args = length_params
        # context_name = length_args[0]
        response_length = apipaths.LENGTH_ATTRIBUTES[response_type]
        response_size = request_size + 1

        number_of_requests = 100 if no_limit_req else int(G.ADDON.getSettingInt('page_results') / 45)
        perpetual_range_start = int(perpetual_range_start) if perpetual_range_start else 0
        range_start = perpetual_range_start
        range_end = range_start + request_size
        merged_response = {}

        for n_req in range(number_of_requests):
            path_response = self.path_request(_set_range_selector(paths, range_start, range_end))
            if not path_response:
                break
            if not common.check_path_exists(length_args, path_response):
                # It may happen that the number of items to be received
                # is equal to the number of the response_size
                # so a second round will be performed, which will return an empty list
                break
            common.merge_dicts(path_response, merged_response)
            response_count = response_length(path_response, *length_args)
            if response_count < response_size:
                # There are no other elements to request
                break

            range_start += response_size
            if n_req == (number_of_requests - 1):
                merged_response['_perpetual_range_selector'] = {'next_start': range_start}
                LOG.debug('{} has other elements, added _perpetual_range_selector item', response_type)
            else:
                range_end = range_start + request_size

        if perpetual_range_start > 0:
            previous_start = perpetual_range_start - (response_size * number_of_requests)
            if '_perpetual_range_selector' in merged_response:
                merged_response['_perpetual_range_selector']['previous_start'] = previous_start
            else:
                merged_response['_perpetual_range_selector'] = {'previous_start': previous_start}
        return merged_response

    def perpetual_path_request_switch_profiles(self, paths, length_params, perpetual_range_start=None,
                                               request_size=apipaths.PATH_REQUEST_SIZE_STD, no_limit_req=False):
        """
        Perform a perpetual path request by activating a specified profile,
        Used exclusively to get My List of a profile other than the current one
        """
        # Profile chosen by the user for the synchronization from which to get My List videos
        mylist_profile_guid = G.SHARED_DB.get_value('sync_mylist_profile_guid',
                                                    G.LOCAL_DB.get_guid_owner_profile())
        # Current profile active
        current_profile_guid = G.LOCAL_DB.get_active_profile_guid()
        # Switch profile (only if necessary) in order to get My List videos
        self.external_func_activate_profile(mylist_profile_guid)  # pylint: disable=not-callable
        # Get the My List data
        path_response = self.perpetual_path_request(paths, length_params, perpetual_range_start,
                                                    request_size, no_limit_req)
        if mylist_profile_guid != current_profile_guid:
            # Reactive again the previous profile
            self.external_func_activate_profile(current_profile_guid)  # pylint: disable=not-callable
        return path_response

    @measure_exec_time_decorator(is_immediate=True)
    def callpath_request(self, callpaths, params=None, path_suffixs=None, path=None):
        """Perform a callPath request against the Shakti API"""
        LOG.debug('Executing callPath request: {} params: {} path_suffixs: {}',
                  callpaths, params, path_suffixs)
        custom_params = {
            'falcor_server': '0.1.0',
            'method': 'call',
            'withSize': 'true',
            'materialize': 'true',
        }
        # Use separators with dumps because Netflix rejects spaces
        data = 'callPath=' + '&callPath='.join(
            json.dumps(callpath, separators=(',', ':')) for callpath in callpaths)
        if params:
            # The data to pass on 'params' must not be formatted with json.dumps because it is not full compatible
            #          if the request have wrong data will raise error 401
            #          if the parameters are not formatted correctly will raise error 401
            data += '&param=' + '&param='.join(params)
        if path:
            data += '&path=' + json.dumps(path, separators=(',', ':'))
        if path_suffixs:
            data += '&pathSuffix=' + '&pathSuffix='.join(
                json.dumps(path_suffix, separators=(',', ':')) for path_suffix in path_suffixs)
        # LOG.debug('callPath request data: {}', data)
        response_data = self.post_safe(
            endpoint='shakti',
            params=custom_params,
            data=data)
        return response_data['jsonGraph']


def _set_range_selector(paths, range_start, range_end):
    """
    Replace the RANGE_PLACEHOLDER with an actual dict:
    {'from': range_start, 'to': range_end}
    """
    from copy import deepcopy
    # Make a deepcopy because we don't want to lose the original paths with the placeholder
    ranged_paths = deepcopy(paths)
    for path in ranged_paths:
        try:
            path[path.index(apipaths.RANGE_PLACEHOLDER)] = {'from': range_start, 'to': range_end}
        except ValueError:
            pass
    return ranged_paths
