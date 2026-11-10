#!/usr/bin/env python3
"""Run without Kodi or Netflix; synthetic GraphQL artwork mapping smoke test.

Execute from the repository root:
    python3 contrib/renetrox/test_artwork_offline.py
"""
import importlib.util
from pathlib import Path
import sys
import types

root = Path(__file__).resolve().parents[2]
module_path = root / 'resources/lib/services/nfsession/renetrox_artwork_graphql.py'

for name in ('resources', 'resources.lib', 'resources.lib.utils',
             'resources.lib.utils.logging'):
    stub = types.ModuleType(name)
    stub.__path__ = []
    sys.modules[name] = stub


class Logger:
    def warn(self, *args):
        pass


sys.modules['resources.lib.utils.logging'].LOG = Logger()
spec = importlib.util.spec_from_file_location('artwork_under_test', module_path)
artwork = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artwork)

image = 'https://occ-0-1234.1.nflxso.net/art/legit.jpg'
alien = 'https://other.example.org/art/not-netflix.jpg'
data = {'movie': {'videoId': 123, 'images': [
    {'__typename': 'Image', 'key': 'StoryArt|abc|es',
     'url': image, 'width': 1280},
    {'__typename': 'Image', 'key': 'sdp|abc|es',
     'url': image, 'width': 665},
    {'__typename': 'Image', 'key': 'sdp|other|es',
     'url': alien, 'width': 8000},
    {'__typename': 'Image', 'key': 'LOGO_BRANDED_HORIZONTAL|abc|es',
     'url': image, 'width': 550},
    {'videoId': 999, 'promo': {'__typename': 'Image',
     'key': 'StoryArt|other|es',
     'url': 'https://occ-0-1234.1.nflxso.net/art/wrong.jpg',
     'width': 9999}},
]}}
expected = {'fanart': image, 'thumb': image,
            'landscape': image, 'clearlogo': image}
assert artwork.extract_art(data, 123) == expected
assert artwork.extract_art(data, 999)['fanart'].endswith('/wrong.jpg')
assert artwork.extract_art(data, 124) == {
    'fanart': '', 'thumb': '', 'landscape': '', 'clearlogo': ''}
assert not artwork._valid_image_url('http://occ-0-1234.1.nflxso.net/art/x')
assert not artwork._valid_image_url('https://nflxso.net.bad.example.org/x')


class Session:
    def post_safe(self, endpoint, data):
        assert endpoint == 'rnx_graphql_art'
        assert data['operationName'] == 'DetailModal'
        assert data['variables']['videoId'] == 123
        return {'data': data_fixture}


data_fixture = data
assert artwork.fetch_art(Session(), 123) == {
    'status': 'ok', 'art': expected}


class Expired:
    def post_safe(self, endpoint, data):
        return {'errors': [{'message': 'UNAUTHENTICATED'}]}


assert artwork.fetch_art(Expired(), 123)['status'] == 'unauthenticated'
print('PASS: GraphQL artwork extraction, entity scoping, CDN validation and error handling')
