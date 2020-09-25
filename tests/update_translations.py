#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys

import polib

# Load po-files
translated = polib.pofile(sys.argv[1], wrapwidth=0)
english = polib.pofile(sys.argv[2], wrapwidth=0)

for entry in english:
    # Find a translation
    translation = translated.find(entry.msgctxt, 'msgctxt')

    if translation:
        entry.msgstr = translation.msgstr

english.metadata = translated.metadata

# Save it now over the translation
english.save(sys.argv[1])
