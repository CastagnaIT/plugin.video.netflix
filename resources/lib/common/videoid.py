# -*- coding: utf-8 -*-
"""Universal representation of VideoIds"""
from __future__ import unicode_literals

from functools import wraps


class InvalidVideoId(Exception):
    """The provided video id is not valid"""
    pass


class VideoId(object):
    """Universal representation of a video id. Video IDs can be of multiple
    types:
    - movie: a single identifier only for movieid, all other values must be
             None
    - show: a single identifier only for tvshowid, all other values must be
            None
    - season: identifiers for seasonid and tvshowid, all other values must
              be None
    - episode: identifiers for episodeid, seasonid and tvshowid, all other
               values must be None
    - no type: a single identifier only for videoid. If this is used, there's
               no validation and other supplied values will be ignored."""
    # pylint: disable=too-many-arguments
    MOVIE = 'movie'
    SHOW = 'show'
    SEASON = 'season'
    EPISODE = 'episode'
    UNSPECIFIED = 'unspecified'
    TV_TYPES = [SHOW, SEASON, EPISODE]

    REPR_FORMAT = ('{mediatype}(videoid={videoid},movieid={movieid},'
                   'episodeid={episodeid},seasonid={seasonid},'
                   'tvshowid={tvshowid})')

    def __init__(self, movieid=None, episodeid=None, seasonid=None,
                 tvshowid=None, videoid=None):
        if videoid:
            self.videoid = videoid
            self.id_values = (None, None, None, None)
        else:
            self.videoid = None
            self.id_values = (movieid, episodeid, seasonid, tvshowid)
            for id_index in range(0, len(self.id_values) - 1):
                if self._validate(id_index):
                    break

    @classmethod
    def from_path(cls, pathitems):
        """Create a VideoId instance from pathitems"""
        if pathitems[0] == 'movie':
            return cls(movieid=pathitems[1])
        elif pathitems[0] == 'show':
            return cls(tvshowid=pathitems[1],
                       seasonid=pathitems[3] if len(pathitems) > 3 else None,
                       episodeid=pathitems[5] if len(pathitems) > 5 else None)
        return cls(videoid=pathitems[0])

    @property
    def value(self):
        """The value of this videoId"""
        return (self.videoid
                if self.videoid
                else next(id_value for id_value in self.id_values if id_value))

    @property
    def movieid(self):
        """The seasonid value, if it exists"""
        return None if self.videoid else self.id_values[0]

    @property
    def episodeid(self):
        """The seasonid value, if it exists"""
        return None if self.videoid else self.id_values[1]

    @property
    def seasonid(self):
        """The seasonid value, if it exists"""
        return None if self.videoid else self.id_values[2]

    @property
    def tvshowid(self):
        """The tvshowid value, if it exists"""
        return None if self.videoid else self.id_values[3]

    @property
    def mediatype(self):
        """The mediatype this VideoId instance represents.
        Either movie, show, season, episode or unknown"""
        return (self.UNSPECIFIED
                if self.videoid
                else (self.MOVIE, self.EPISODE, self.SEASON, self.SHOW)[
                    next(i
                         for i, v in enumerate(self.id_values)
                         if v is not None)])

    def to_path(self):
        """Generate a valid pathitems list (['show', tvshowid, ...]) from
        this instance"""
        if self.videoid:
            return [self.videoid]
        if self.movieid:
            return [self.MOVIE, self.movieid]

        pathitems = [self.SHOW, self.tvshowid]
        if self.seasonid:
            pathitems.extend([self.SEASON, self.seasonid])
        if self.episodeid:
            pathitems.extend([self.EPISODE, self.episodeid])
        return pathitems

    def to_list(self):
        """Generate a list representation that can be used with get_path"""
        if self.videoid:
            return self.videoid
        path = [id_part for id_part in self.id_values if id_part]
        if len(path) > 1:
            path.reverse()
        return path

    def to_dict(self):
        """Return a dict containing the relevant properties of this
        instance"""
        result = {'mediatype': self.mediatype}
        if self.videoid:
            result['videoid'] = self.videoid
            return result
        if self.movieid:
            result['movieid'] = self.movieid
            return result
        result.update({prop: self.__getattribute__(prop)
                       for prop in ['tvshowid', 'seasonid', 'episodeid']
                       if self.__getattribute__(prop) is not None})
        return result

    def derive_season(self, seasonid):
        """Return a new VideoId instance that represents the given season
        of this show. Raises InvalidVideoId is this instance does not
        represent a show."""
        if self.mediatype != VideoId.SHOW:
            raise InvalidVideoId('Cannot derive season VideoId from {}'
                                 .format(self))
        return type(self)(tvshowid=self.tvshowid, seasonid=unicode(seasonid))

    def derive_episode(self, episodeid):
        """Return a new VideoId instance that represents the given episode
        of this season. Raises InvalidVideoId is this instance does not
        represent a season."""
        if self.mediatype != VideoId.SEASON:
            raise InvalidVideoId('Cannot derive episode VideoId from {}'
                                 .format(self))
        return type(self)(tvshowid=self.tvshowid, seasonid=self.seasonid,
                          episodeid=unicode(episodeid))

    def _validate(self, index):
        if self.id_values[index]:
            if ((not all(v is None for v in self.id_values[1:])
                 if index == 0
                 else None in self.id_values[index:])):
                raise InvalidVideoId(self.id_values)
            return True  # Validation successful
        if index == len(self.id_values):
            raise InvalidVideoId(self.id_values)
        return False  # Validation does not apply

    def __str__(self):
        return '{}_{}'.format(self.mediatype, self.value)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return (self.videoid == other.videoid and
                self.id_values == other.id_values)

    def __neq__(self, other):
        return not self.__eq__(other)


def inject_video_id(path_offset, pathitems_arg='pathitems',
                    inject_remaining_pathitems=False):
    """Decorator that converts a pathitems argument into a VideoId
    and injects this into the decorated function instead. Pathitems
    that are to be converted into a video id must be passed into
    the function via kwarg defined by pathitems_arg (default=pathitems)"""
    # pylint: disable=missing-docstring
    def injecting_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                kwargs['videoid'] = VideoId.from_path(
                    kwargs[pathitems_arg][path_offset:])
                if inject_remaining_pathitems:
                    kwargs[pathitems_arg] = kwargs[pathitems_arg][:path_offset]
                else:
                    del kwargs[pathitems_arg]
            except KeyError:
                raise Exception('Pathitems must be passed as kwarg {}'
                                .format(pathitems_arg))
            return func(*args, **kwargs)
        return wrapper
    return injecting_decorator
