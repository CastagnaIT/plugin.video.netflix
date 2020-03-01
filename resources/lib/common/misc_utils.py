# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Miscellanneous utility functions

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
# pylint: disable=unused-import
from __future__ import absolute_import, division, unicode_literals
from functools import wraps
from time import clock
from future.utils import iteritems

try:  # Python 2
    from itertools import imap as map  # pylint: disable=redefined-builtin
except ImportError:
    pass

try:  # Python 3
    from io import StringIO
except ImportError:  # Python 2
    from StringIO import StringIO

try:  # Python 3
    from urllib.parse import quote, urlencode
except ImportError:  # Python 2
    from urllib import urlencode
    from urllib2 import quote

import xbmc
import xbmcgui

from resources.lib.globals import g
from .logging import debug, info, error
from .kodiops import get_local_string


def find(value_to_find, attribute, search_space):
    """Find a video with matching id in a dict or list"""
    for video in search_space:
        if video[attribute] == value_to_find:
            return video
    raise KeyError('Metadata for {} does not exist'.format(value_to_find))


def find_episode_metadata(videoid, metadata):
    """Find metadata for a specific episode within a show metadata dict"""
    season = find(int(videoid.seasonid), 'id', metadata['seasons'])
    return (find(int(videoid.episodeid), 'id', season.get('episodes', {})),
            season)


def select_port(service):
    """Select a port for a server and store it in the settings"""
    port = select_unused_port()
    g.LOCAL_DB.set_value('{}_service_port'.format(service.lower()), port)
    info('[{}] Picked Port: {}'.format(service, port))
    return port


def select_unused_port():
    """
    Helper function to select an unused port on the host machine

    :return: int - Free port
    """
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))
    _, port = sock.getsockname()
    sock.close()
    return port


def get_class_methods(class_item=None):
    """
    Returns the class methods of agiven class object

    :param class_item: Class item to introspect
    :type class_item: object
    :returns: list -- Class methods
    """
    from types import FunctionType
    _type = FunctionType
    return [x
            for x, y in iteritems(class_item.__dict__)
            if isinstance(y, _type)]


def get_user_agent(enable_android_mediaflag_fix=False):
    """
    Determines the user agent string for the current platform.
    Needed to retrieve a valid ESN (except for Android, where the ESN can be generated locally)

    :returns: str -- User agent string
    """
    system = get_system_platform()
    if enable_android_mediaflag_fix and system == 'android' and is_device_4k_capable():
        # The UA affects not only the ESNs in the login, but also the video details,
        # so the UAs seem refer to exactly to these conditions: https://help.netflix.com/en/node/23742
        # This workaround is needed because currently we do not login through the netflix native android API,
        # but redirect everything through the website APIs, and the website APIs do not really support android.
        # Then on android usually we use the 'arm' UA which refers to chrome os, but this is limited to 1080P, so the
        # labels on the 4K devices appears wrong (in the Kodi skin the 4K videos have 1080P media flags instead of 4K),
        # the Windows UA is not limited, so we can use it to get the right video media flags.
        system = 'windows'

    chrome_version = 'Chrome/78.0.3904.92'
    base = 'Mozilla/5.0 '
    base += '%PL% '
    base += 'AppleWebKit/537.36 (KHTML, like Gecko) '
    base += '%CH_VER% Safari/537.36'.replace('%CH_VER%', chrome_version)

    if system in ['osx', 'ios', 'tvos']:
        return base.replace('%PL%', '(Macintosh; Intel Mac OS X 10_14_6)')
    if system in ['windows', 'uwp']:
        return base.replace('%PL%', '(Windows NT 10; Win64; x64)')
    # ARM based Linux
    if get_machine().startswith('arm'):
        # Last number is the platform version of Chrome OS
        return base.replace('%PL%', '(X11; CrOS armv7l 12371.89.0)')
    # x86 Linux
    return base.replace('%PL%', '(X11; Linux x86_64)')


def build_url(pathitems=None, videoid=None, params=None, mode=None):
    """Build a plugin URL from pathitems and query parameters.
    Add videoid to the path if it's present."""
    if not (pathitems or videoid):
        raise ValueError('Either pathitems or videoid must be set.')
    path = '{netloc}/{path}/{qs}'.format(
        netloc=g.BASE_URL,
        path=_encode_path(mode, pathitems, videoid),
        qs=_encode_params(params))
    return path


def _expand_mode(mode):
    return [mode] if mode else []


def _expand_videoid(videoid):
    return videoid.to_path() if videoid else []


def _encode_path(mode, pathitems, videoid):
    return quote(
        '/'.join(_expand_mode(mode) +
                 (pathitems or []) +
                 _expand_videoid(videoid)).encode('utf-8'))


def _encode_params(params):
    return ('?' + urlencode(params)) if params else ''


def is_numeric(string):
    """Return true if string represents an integer, else false"""
    try:
        int(string)
    except ValueError:
        return False
    return True


def strp(value, form):
    """
    Helper function to safely create datetime objects from strings

    :return: datetime - parsed datetime object
    """
    # pylint: disable=broad-except
    from datetime import datetime
    def_value = datetime.utcfromtimestamp(0)
    try:
        return datetime.strptime(value, form)
    except TypeError:
        try:
            from time import strptime
            return datetime(*(strptime(value, form)[0:6]))
        except ValueError:
            return def_value
    except Exception:
        return def_value


def execute_tasks(title, tasks, task_handler, **kwargs):
    """Run all tasks through task_handler and display a progress
    dialog in the GUI. Additional kwargs will be passed into task_handler
    on each invocation.
    Returns a list of errors that occured during execution of tasks."""
    errors = []
    notify_errors = kwargs.pop('notify_errors', False)
    progress = xbmcgui.DialogProgress()
    progress.create(title)
    for task_num, task in enumerate(tasks):
        # pylint: disable=broad-except
        task_title = task.get('title', 'Unknown Task')
        progress.update(percent=int(task_num * 100 / len(tasks)),
                        line1=task_title)
#        xbmc.sleep(25)
        if progress.iscanceled():
            break
        if not task:
            continue
        try:
            task_handler(task, **kwargs)
        except Exception as exc:
            import traceback
            error(traceback.format_exc())
            errors.append({
                'task_title': task_title,
                'error': '{}: {}'.format(type(exc).__name__, exc)})
    _show_errors(notify_errors, errors)
    return errors


def _show_errors(notify_errors, errors):
    if notify_errors and errors:
        xbmcgui.Dialog().ok(get_local_string(0),
                            '\n'.join(['{} ({})'.format(err['task_title'],
                                                        err['error'])
                                       for err in errors]))


# def compress_data(data):
#    """GZIP and b64 encode data"""
#    out = StringIO()
#    with gzip.GzipFile(fileobj=out, mode='w') as outh:
#        outh.write(data)
#    return base64.standard_b64encode(out.getvalue())


def merge_dicts(dict_to_merge, merged_dict):
    """Recursively merge the contents of dict_to_merge into merged_dict.
    Values that are already present in merged_dict will be overwritten
    if they are also present in dict_to_merge"""
    for key, value in iteritems(dict_to_merge):
        if isinstance(merged_dict.get(key), dict):
            merge_dicts(value, merged_dict[key])
        else:
            merged_dict[key] = value
    return merged_dict


def compare_dicts(dict_a, dict_b, excluded_keys=None):
    """
    Compare two dict with same keys, with optional keys to exclude from compare
    """
    if excluded_keys is None:
        excluded_keys = []
    return all(dict_a[k] == dict_b[k] for k in dict_a if k not in excluded_keys)


def any_value_except(mapping, excluded_keys):
    """Return a random value from a dict that is not associated with
    excluded_key. Raises StopIteration if there are no other keys than
    excluded_key"""
    return next(mapping[key] for key in mapping if key not in excluded_keys)


def enclose_quotes(content):
    return '"' + content + '"'


def time_execution(immediate):
    """A decorator that wraps a function call and times its execution"""
    # pylint: disable=missing-docstring
    def time_execution_decorator(func):
        @wraps(func)
        def timing_wrapper(*args, **kwargs):
            g.add_time_trace_level()
            start = clock()
            try:
                return func(*args, **kwargs)
            finally:
                if g.TIME_TRACE_ENABLED:
                    execution_time = int((clock() - start) * 1000)
                    if immediate:
                        debug('Call to {} took {}ms'
                              .format(func.__name__, execution_time))
                    else:
                        g.TIME_TRACE.append([func.__name__, execution_time,
                                             g.time_trace_level])
                g.remove_time_trace_level()
        return timing_wrapper
    return time_execution_decorator


def log_time_trace():
    """Write the time tracing info to the debug log"""
    if not g.TIME_TRACE_ENABLED:
        return

    time_trace = ['Execution time info for this run:\n']
    g.TIME_TRACE.reverse()
    for trace in g.TIME_TRACE:
        time_trace.append(' ' * trace[2])
        time_trace.append(format(trace[0], '<30'))
        time_trace.append('{:>5} ms\n'.format(trace[1]))
    debug(''.join(time_trace))
    g.reset_time_trace()


def is_edge_esn(esn):
    """Return True if the esn is an EDGE esn"""
    return esn.startswith('NFCDIE-02-')


def is_minimum_version(version, min_version):
    """Return True if version is equal or greater to min_version"""
    return list(map(int, version.split('.'))) >= list(map(int, min_version.split('.')))


def is_less_version(version, max_version):
    """Return True if version is less to max_version"""
    return list(map(int, version.split('.'))) < list(map(int, max_version.split('.')))


def make_list(arg):
    """Return a list with arg as its member or arg if arg is already a list.
    Returns an empty list if arg is None"""
    return (arg
            if isinstance(arg, list)
            else ([arg]
                  if arg is not None
                  else []))


def convert_seconds_to_hms_str(time):
    h = int(time // 3600)
    time %= 3600
    m = int(time // 60)
    s = int(time % 60)
    return '{:02d}:{:02d}:{:02d}'.format(h, m, s)


def remove_html_tags(raw_html):
    import re
    h = re.compile('<.*?>')
    text = re.sub(h, '', raw_html)
    return text


def censure(value, length=3):
    """Censor part of the string with asterisks"""
    if not value:
        return value
    return value[:-length] + '*' * length


def is_device_4k_capable():
    """Check if the device is 4k capable"""
    # Currently only on android is it possible to use 4K
    if get_system_platform() == 'android':
        from re import findall
        from resources.lib.database.db_utils import TABLE_SESSION
        # Check if the drm has security level L1
        is_drm_l1_security_level = g.LOCAL_DB.get_value('drm_security_level', '', table=TABLE_SESSION) == 'L1'
        # Check if HDCP level is 2.2 or up
        drm_hdcp_level = findall('\\d+\\.\\d+', g.LOCAL_DB.get_value('drm_hdcp_level', '', table=TABLE_SESSION))
        hdcp_4k_capable = drm_hdcp_level and float(drm_hdcp_level[0]) >= 2.2
        return is_drm_l1_security_level and hdcp_4k_capable
    return False


def run_threaded(non_blocking, target_func, *args, **kwargs):
    """Call a function in a thread, when specified"""
    if not non_blocking:
        target_func(*args, **kwargs)
        return
    from threading import Thread
    thread = Thread(target=target_func, args=args, kwargs=kwargs)
    thread.start()


def get_machine():
    """Get machine architecture"""
    from platform import machine
    try:
        return machine()
    except Exception:  # pylint: disable=broad-except
        # Due to OS restrictions on 'ios' and 'tvos' this generate an exception
        # See python limits in the wiki development page
        # Fallback with a generic arm
        return 'arm'


def get_system_platform():
    if not hasattr(get_system_platform, 'cached'):
        platform = "unknown"
        if xbmc.getCondVisibility('system.platform.linux') and not xbmc.getCondVisibility('system.platform.android'):
            if xbmc.getCondVisibility('system.platform.linux.raspberrypi'):
                platform = "linux raspberrypi"
            else:
                platform = "linux"
        elif xbmc.getCondVisibility('system.platform.linux') and xbmc.getCondVisibility('system.platform.android'):
            platform = "android"
        elif xbmc.getCondVisibility('system.platform.uwp'):
            platform = "uwp"
        elif xbmc.getCondVisibility('system.platform.windows'):
            platform = "windows"
        elif xbmc.getCondVisibility('system.platform.osx'):
            platform = "osx"
        elif xbmc.getCondVisibility('system.platform.ios'):
            platform = "ios"
        elif xbmc.getCondVisibility('system.platform.tvos'):  # Supported only on Kodi 19.x
            platform = "tvos"
        get_system_platform.cached = platform
    return get_system_platform.cached


class GetKodiVersion(object):
    """Get the kodi version, git date, stage name"""
    # Examples of some types of supported strings:
    # 10.1 Git:Unknown                       PRE-11.0 Git:Unknown                  11.0-BETA1 Git:20111222-22ad8e4
    # 18.1-RC1 Git:20190211-379f5f9903       19.0-ALPHA1 Git:20190419-c963b64487

    def __init__(self):
        self._build_version = xbmc.getInfoLabel('System.BuildVersion')

    @property
    def version(self):
        import re
        result = re.search('\\d+\\.\\d+?(?=(\\s|-))', self._build_version)
        return result.group(0) if result else 'Unknown'

    @property
    def date(self):
        import re
        result = re.search('(Git:)(\\d+?(?=(-|$)))', self._build_version)
        return int(result.group(2)) if result and len(result.groups()) >= 2 else None

    @property
    def stage(self):
        import re
        result = re.search('(\\d+\\.\\d+-)(.+)(?=\\s)', self._build_version)
        if not result:
            result = re.search('^(.+)(-\\d+\\.\\d+)', self._build_version)
            return result.group(1) if result else ''
        return result.group(2) if result else ''


def update_cache_videoid_runtime(window_cls):
    """Try to update the bookmarkPosition value in cache data in order to get a updated watched status/resume time"""
    # Other details in:
    # progress_manager.py method: _save_resume_time()
    # infolabels.py method: _set_progress_status()
    runtime = window_cls.getProperty('nf_playback_resume_time')
    if runtime and runtime.isdigit():
        from resources.lib.api.data_types import VideoList, VideoListSorted, EpisodeList, SearchVideoList
        from resources.lib.cache import CacheMiss
        from resources.lib.database.db_utils import TABLE_SESSION
        from resources.lib.common import VideoId
        cache_last_dir_call = g.LOCAL_DB.get_value('cache_last_directory_call', {}, table=TABLE_SESSION)
        if not cache_last_dir_call:
            return
        videoid = VideoId.from_dict(g.LOCAL_DB.get_value('last_videoid_played', {}, table=TABLE_SESSION))
        try:
            data_object = g.CACHE.get(cache_last_dir_call['bucket'], cache_last_dir_call['identifier'])
            if isinstance(data_object, (VideoList, VideoListSorted, SearchVideoList)):
                data_object.videos[str(videoid.value)]['bookmarkPosition'] = int(runtime)
            elif isinstance(data_object, EpisodeList):
                data_object.episodes[str(videoid.value)]['bookmarkPosition'] = int(runtime)
            else:
                error('update_cache_videoid_runtime: cache object not mapped, bookmarkPosition not updated')
            g.CACHE.update(cache_last_dir_call['bucket'], cache_last_dir_call['identifier'], data_object,
                           cache_last_dir_call['to_disk'])
        except CacheMiss:
            # No more valid cache, manual update not needed
            pass
        window_cls.setProperty('nf_playback_resume_time', '')
