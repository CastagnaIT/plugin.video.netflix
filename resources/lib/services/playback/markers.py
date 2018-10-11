# -*- coding: utf-8 -*-

"""Various timeline markers provided by Netflix"""
from __future__ import unicode_literals

SKIPPABLE_SECTIONS = {'credit': 30076, 'recap': 30077}
OFFSET_WATCHED_TO_END = 'watchedToEndOffset'
OFFSET_CREDITS = 'creditsOffset'

def get_offset_markers(metadata):
    """Extract offset timeline markers from metadata if they exist"""
    return {
        marker: metadata[marker]
        for marker in [OFFSET_CREDITS, OFFSET_WATCHED_TO_END]
        if metadata.get(marker) is not None
    }


def get_section_markers(metadata):
    """Extract section start and end markers from metadata if they exist"""
    return {
        section: {
            'start': int(metadata['creditMarkers'][section]['start'] /
                         1000),
            'end': int(metadata['creditMarkers'][section]['end'] / 1000)
        }
        for section in SKIPPABLE_SECTIONS
        if (None not in metadata['creditMarkers'][section].values() and
            any(i > 0 for i in metadata['creditMarkers'][section].values()))
    }
