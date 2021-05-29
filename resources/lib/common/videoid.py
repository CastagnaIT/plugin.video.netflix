# -*- coding: utf-8 -*-
"""
    Copyright (C) 2017 Sebastian Golasch (plugin.video.netflix)
    Copyright (C) 2018 Caphm (original implementation module)
    Universal representation of VideoIds

    SPDX-License-Identifier: MIT
    See LICENSES/MIT.md for more information.
"""
from functools import wraps

from .exceptions import InvalidVideoId


class VideoId:
    """Universal representation of a video id. Video IDs can be of multiple types:
    - supplemental: a single identifier only for supplementalid, all other values must be None
    - movie: a single identifier only for movieid, all other values must be None
    - show: a single identifier only for tvshowid, all other values must be None
    - season: identifiers for seasonid and tvshowid, all other values must be None
    - episode: identifiers for episodeid, seasonid and tvshowid, all other values must be None
    - unspecified: a single identifier only for videoid, all other values must be None"""
    SUPPLEMENTAL = 'supplemental'
    MOVIE = 'movie'
    SHOW = 'show'
    SEASON = 'season'
    EPISODE = 'episode'
    UNSPECIFIED = 'unspecified'
    TV_TYPES = [SHOW, SEASON, EPISODE]

    VALIDATION_MASKS = {
        0b100000: UNSPECIFIED,
        0b010000: SUPPLEMENTAL,
        0b001000: MOVIE,
        0b000001: SHOW,
        0b000011: SEASON,
        0b000111: EPISODE
    }

    def __init__(self, **kwargs):
        self._id_values = _get_unicode_kwargs(kwargs)
        # debug('VideoId validation values: {}'.format(self._id_values))
        self._validate()
        self._menu_parameters = MenuIdParameters(self._assigned_id_values()[0])

    def _validate(self):
        validation_mask = 0
        # Example: ('39c9a88a-a56e-4c8a-921c-3c1f86c0ebb9_62682962X28X6548X1551537755876', None, None, None, None)
        # This result in a VALIDATION_MASKS 'unspecified'. Because text data is on index 0, and others are None
        for index, value in enumerate(self._id_values):
            validation_mask |= (value is not None) << (5 - index)
        try:
            self._mediatype = VideoId.VALIDATION_MASKS[validation_mask]
        except KeyError as exc:
            raise InvalidVideoId from exc

    @classmethod
    def from_path(cls, pathitems):
        """Create a VideoId instance from pathitems"""
        if pathitems[0] == VideoId.MOVIE:
            return cls(movieid=pathitems[1])
        if pathitems[0] == VideoId.SHOW:
            return cls(tvshowid=_path_attr(pathitems, 1),
                       seasonid=_path_attr(pathitems, 3),
                       episodeid=_path_attr(pathitems, 5))
        if pathitems[0] == VideoId.SUPPLEMENTAL:
            return cls(supplementalid=pathitems[1])
        return cls(videoid=pathitems[0])

    @classmethod
    def from_dict(cls, dict_items):
        """Create a VideoId instance from a dict items"""
        mediatype = dict_items['mediatype']
        if mediatype == VideoId.MOVIE:
            return cls(movieid=dict_items['movieid'])
        if mediatype in VideoId.TV_TYPES:
            return cls(tvshowid=_path_attr_dict(dict_items, 'tvshowid'),
                       seasonid=_path_attr_dict(dict_items, 'seasonid'),
                       episodeid=_path_attr_dict(dict_items, 'episodeid'))
        if mediatype == VideoId.SUPPLEMENTAL:
            return cls(supplementalid=dict_items['supplementalid'])
        raise InvalidVideoId

    @classmethod
    def from_videolist_item(cls, video):
        """Create a VideoId from a video item contained in a video list path response"""
        mediatype = video['summary']['type']
        video_id = video['summary']['id']
        if mediatype == VideoId.MOVIE:
            return cls(movieid=video_id)
        if mediatype == VideoId.SHOW:
            return cls(tvshowid=video_id)
        if mediatype == VideoId.SUPPLEMENTAL:
            return cls(supplementalid=video_id)
        raise InvalidVideoId(
            'Can only construct a VideoId from a show/movie/supplemental item')

    @property
    def value(self):
        """The value of this VideoId"""
        return self._assigned_id_values()[0]

    @property
    def menu_parameters(self):
        """The menu parameters of the videoid value, if it exists"""
        return self._menu_parameters

    @property
    def videoid(self):
        """The videoid value, if it exists"""
        return self._id_values[0]

    @property
    def supplementalid(self):
        """The supplemental value, if it exists"""
        return self._id_values[1]

    @property
    def movieid(self):
        """The movieid value, if it exists"""
        return self._id_values[2]

    @property
    def episodeid(self):
        """The episodeid value, if it exists"""
        return self._id_values[3]

    @property
    def seasonid(self):
        """The seasonid value, if it exists"""
        return self._id_values[4]

    @property
    def tvshowid(self):
        """The tvshowid value, if it exists"""
        return self._id_values[5]

    @property
    def mediatype(self):
        """The mediatype this VideoId instance represents.
        Either movie, show, season, episode, supplemental or unspecified"""
        return self._mediatype

    def convert_old_videoid_type(self):
        """
        If the data contained in to videoid comes from the previous version
        of the videoid class (without supplementalid), then convert the class object
        to the new type of class or else return same class
        """
        if len(self._id_values) == 5:
            videoid_dict = {
                'mediatype': self._mediatype,
                'movieid': self._id_values[1],
                'episodeid': self._id_values[2],
                'seasonid': self._id_values[3],
                'tvshowid': self._id_values[4]
            }
            return VideoId.from_dict(videoid_dict)
        return self

    def to_string(self):
        """Generate a valid pathitems as string ('show'/tvshowid/...) from this instance"""
        if self.videoid:
            return self.videoid
        if self.movieid:
            return '/'.join([self.MOVIE, self.movieid])
        if self.supplementalid:
            return '/'.join([self.SUPPLEMENTAL, self.supplementalid])
        pathitems = [self.SHOW, self.tvshowid]
        if self.seasonid:
            pathitems.extend([self.SEASON, self.seasonid])
        if self.episodeid:
            pathitems.extend([self.EPISODE, self.episodeid])
        return '/'.join(pathitems)

    def to_path(self):
        """Generate a valid pathitems list (['show', tvshowid, ...]) from
        this instance"""
        if self.videoid:
            return [self.videoid]
        if self.movieid:
            return [self.MOVIE, self.movieid]
        if self.supplementalid:
            return [self.SUPPLEMENTAL, self.supplementalid]

        pathitems = [self.SHOW, self.tvshowid]
        if self.seasonid:
            pathitems.extend([self.SEASON, self.seasonid])
        if self.episodeid:
            pathitems.extend([self.EPISODE, self.episodeid])
        return pathitems

    def to_list(self):
        """Generate a list representation that can be used with get_path"""
        path = self._assigned_id_values()
        if len(path) > 1:
            path.reverse()
        return path

    def to_dict(self):
        """Return a dict containing the relevant properties of this
        instance"""
        result = {'mediatype': self.mediatype}
        result.update({prop: self.__getattribute__(prop)  # pylint: disable=no-member
                       for prop in ['videoid', 'supplementalid', 'movieid',
                                    'tvshowid', 'seasonid', 'episodeid']
                       if self.__getattribute__(prop) is not None})  # pylint: disable=no-member
        return result

    def derive_season(self, seasonid):
        """Return a new VideoId instance that represents the given season
        of this show. Raises InvalidVideoId is this instance does not
        represent a show."""
        if self.mediatype != VideoId.SHOW:
            raise InvalidVideoId(f'Cannot derive season VideoId from {self}')
        return type(self)(tvshowid=self.tvshowid, seasonid=str(seasonid))

    def derive_episode(self, episodeid):
        """Return a new VideoId instance that represents the given episode
        of this season. Raises InvalidVideoId is this instance does not
        represent a season."""
        if self.mediatype != VideoId.SEASON:
            raise InvalidVideoId(f'Cannot derive episode VideoId from {self}')
        return type(self)(tvshowid=self.tvshowid, seasonid=self.seasonid,
                          episodeid=str(episodeid))

    def derive_parent(self, videoid_type):
        """
        Derive a parent VideoId, you can obtain:
          [tvshow] from season, episode
          [season] from episode
        When it is not possible get a derived VideoId, it is returned the same VideoId instance.

        :param videoid_type: The type of VideoId to be derived
        :return: The parent VideoId of specified type, or when not match the same VideoId instance.
        """
        if videoid_type == VideoId.SHOW:
            if self.mediatype not in [VideoId.SEASON, VideoId.EPISODE]:
                return self
            return type(self)(tvshowid=self.tvshowid)
        if videoid_type == VideoId.SEASON:
            if self.mediatype != VideoId.SEASON:
                return self
            return type(self)(tvshowid=self.tvshowid,
                              seasonid=self.seasonid)
        raise InvalidVideoId(f'VideoId type {videoid_type} not valid')

    def _assigned_id_values(self):
        """Return a list of all id_values that are not None"""
        return [id_value
                for id_value in self._id_values
                if id_value is not None]

    def __str__(self):
        return f'{self.mediatype}_{self.value}'

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        # pylint: disable=protected-access
        if not isinstance(other, VideoId):
            return False
        return self._id_values == other._id_values

    def __neq__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return f'VideoId object [{self}]'


def _get_unicode_kwargs(kwargs):
    # Example of return value: (None, None, '70084801', None, None, None) this is a movieid
    return tuple((str(kwargs[idpart])
                  if kwargs.get(idpart)
                  else None)
                 for idpart
                 in ['videoid', 'supplementalid', 'movieid',
                     'episodeid', 'seasonid', 'tvshowid'])


def _path_attr(pathitems, index):
    return pathitems[index] if len(pathitems) > index else None


def _path_attr_dict(pathitems, key):
    return pathitems[key] if key in pathitems else None


def inject_video_id(path_offset, pathitems_arg='pathitems',
                    inject_remaining_pathitems=False,
                    inject_full_pathitems=False):
    """Decorator that converts a pathitems argument into a VideoId
    and injects this into the decorated function instead. Pathitems
    that are to be converted into a video id must be passed into
    the function via kwarg defined by pathitems_arg (default=pathitems)"""
    # pylint: disable=missing-docstring
    def injecting_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                _path_to_videoid(kwargs, pathitems_arg, path_offset,
                                 inject_remaining_pathitems, inject_full_pathitems)
            except KeyError as exc:
                raise Exception(f'Pathitems must be passed as kwarg {pathitems_arg}') from exc
            return func(*args, **kwargs)
        return wrapper
    return injecting_decorator


def _path_to_videoid(kwargs, pathitems_arg, path_offset,
                     inject_remaining_pathitems, inject_full_pathitems):
    """Parses a VideoId from the kwarg with name defined by pathitems_arg and
    adds it to the kwargs dict.
    If inject_remaining_pathitems is True, the pathitems representing the
    VideoId are stripped from the end of the pathitems and the remaining
    pathitems remain in kwargs. Otherwise, the pathitems will be removed
    from the kwargs dict."""
    kwargs['videoid'] = VideoId.from_path(kwargs[pathitems_arg][path_offset:])
    if inject_remaining_pathitems or inject_full_pathitems:
        if inject_remaining_pathitems:
            kwargs[pathitems_arg] = kwargs[pathitems_arg][:path_offset]
    else:
        del kwargs[pathitems_arg]


class MenuIdParameters:
    """Parse the information grouped in a id value of a menu"""
    # Example:
    # 8f0bcda8-a281-4ca3-9f56-f64ee1d76219_68180357X28X1430972X1551542684270
    # [              request id                   ]X[ type id ]X[ context id ]X[ timestamp ]

    def __init__(self, id_values):
        # Check if the idvalues is a menu id value
        if id_values and id_values.count('-') == 4 and id_values.count('_') == 1 and id_values.count('X') == 3:
            self._is_menu_id = True
            self._splitted_id = id_values.split('X')
        else:
            self._is_menu_id = False

    @property
    def is_menu_id(self):
        """Return True if is a Menu Id"""
        return self._is_menu_id

    @property
    def request_id(self):
        """Return the menu id"""
        return self._splitted_id[0] if self._is_menu_id else None

    @property
    def type_id(self):
        """Return the menu type
        Menu types can be distinguished by numeric code, some example:
        6 - My list menu
        20 - Featured menu
        28 - Generic type of menu that returns tv series
        29 - Generic type of "Other content similar to"
        55 - Original netflix menu
        """
        return self._splitted_id[1] if self._is_menu_id else None

    @property
    def context_id(self):
        """Return the menu context id"""
        return self._splitted_id[2] if self._is_menu_id else None

    @property
    def timestamp(self):
        """Return the menu timestamp"""
        return self._splitted_id[3] if self._is_menu_id else None
