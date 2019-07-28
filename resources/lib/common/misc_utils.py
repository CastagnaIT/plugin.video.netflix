# -*- coding: utf-8 -*-
# pylint: disable=unused-import
"""Miscellanneous utility functions"""
from __future__ import unicode_literals

import traceback
from datetime import datetime
from urllib import urlencode, quote
from functools import wraps
from time import clock
import gzip
import base64
import re
from StringIO import StringIO

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
            for x, y in class_item.__dict__.iteritems()
            if isinstance(y, _type)]


def get_user_agent():
    """
    Determines the user agent string for the current platform.
    Needed to retrieve a valid ESN (except for Android, where the ESN can
    be generated locally)

    :returns: str -- User agent string
    """
    import platform
    chrome_version = 'Chrome/73.0.3683.103'
    base = 'Mozilla/5.0 '
    base += '%PL% '
    base += 'AppleWebKit/537.36 (KHTML, like Gecko) '
    base += '%CH_VER% Safari/537.36'.replace('%CH_VER%', chrome_version)
    system = platform.system()
    # Mac OSX
    if system == 'Darwin':
        return base.replace('%PL%', '(Macintosh; Intel Mac OS X 10_10_1)')
    # Windows
    if system == 'Windows':
        return base.replace('%PL%', '(Windows NT 6.1; WOW64)')
    # ARM based Linux
    if platform.machine().startswith('arm'):
        return base.replace('%PL%', '(X11; CrOS armv7l 7647.78.0)')
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
    from time import strptime
    def_value = datetime.utcfromtimestamp(0)
    try:
        return datetime.strptime(value, form)
    except TypeError:
        try:
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
        xbmc.sleep(25)
        if progress.iscanceled():
            break
        try:
            task_handler(task, **kwargs)
        except Exception as exc:
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


def compress_data(data):
    """GZIP and b64 encode data"""
    out = StringIO()
    with gzip.GzipFile(fileobj=out, mode='w') as outh:
        outh.write(data)
    return base64.standard_b64encode(out.getvalue())


def merge_dicts(dict_to_merge, merged_dict):
    """Recursively merge the contents of dict_to_merge into merged_dict.
    Values that are already present in merged_dict will be overwritten
    if they are also present in dict_to_merge"""
    for key, value in dict_to_merge.iteritems():
        if isinstance(merged_dict.get(key), dict):
            merge_dicts(value, merged_dict[key])
        else:
            merged_dict[key] = value
    return merged_dict


def any_value_except(mapping, excluded_key):
    """Return a random value from a dict that is not associated with
    excluded_key. Raises StopIteration if there are no other keys than
    excluded_key"""
    return next(mapping[key] for key in mapping if key != excluded_key)


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
                              .format(func.func_name, execution_time))
                    else:
                        g.TIME_TRACE.append([func.func_name, execution_time,
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
    return map(int, version.split('.')) >= map(int, min_version.split('.'))


def is_less_version(version, max_version):
    """Return True if version is less to max_version"""
    return map(int, version.split('.')) < map(int, max_version.split('.'))


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
    h = re.compile('<.*?>')
    text = re.sub(h, '', raw_html)
    return text


def get_system_platform():
    platform = "unknown"
    if xbmc.getCondVisibility('system.platform.linux') and not xbmc.getCondVisibility('system.platform.android'):
        platform = "linux"
    elif xbmc.getCondVisibility('system.platform.linux') and xbmc.getCondVisibility('system.platform.android'):
        platform = "android"
    elif xbmc.getCondVisibility('system.platform.xbox'):
        platform = "xbox"
    elif xbmc.getCondVisibility('system.platform.windows'):
        platform = "windows"
    elif xbmc.getCondVisibility('system.platform.osx'):
        platform = "osx"
    elif xbmc.getCondVisibility('system.platform.ios'):
        platform = "ios"
    return platform


class GetKodiVersion(object):
    """Get the kodi version, git date, stage name"""

    def __init__(self):
        # Examples of some types of supported strings:
        # 10.1 Git:Unknown                       PRE-11.0 Git:Unknown                  11.0-BETA1 Git:20111222-22ad8e4
        # 18.1-RC1 Git:20190211-379f5f9903       19.0-ALPHA1 Git:20190419-c963b64487
        build_version_str = xbmc.getInfoLabel('System.BuildVersion')
        re_kodi_version = re.search('\\d+\\.\\d+?(?=(\\s|-))', build_version_str)
        if re_kodi_version:
            self.version = re_kodi_version.group(0)
        else:
            self.version = 'Unknown'
        re_git_date = re.search('(Git:)(\\d+?(?=(-|$)))', build_version_str)
        if re_git_date and len(re_git_date.groups()) >= 2:
            self.date = int(re_git_date.group(2))
        else:
            self.date = 0
        re_stage = re.search('(\\d+\\.\\d+-)(.+)(?=\\s)', build_version_str)
        if not re_stage:
            re_stage = re.search('^(.+)(-\\d+\\.\\d+)', build_version_str)
            self.stage = re_stage.group(1) if re_stage else ''
        else:
            self.stage = re_stage.group(2) if re_stage else ''
