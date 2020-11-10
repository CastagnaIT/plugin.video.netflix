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

    if translation and entry.msgid == translation.msgid:
        entry.msgstr = translation.msgstr

english.metadata = translated.metadata

if sys.platform.startswith('win'):
    # On Windows save the file keeping the Linux return character
    with open(sys.argv[1], 'wb') as _file:
        content = str(english).encode('utf-8')
        content = content.replace(b'\r\n', b'\n')
        _file.write(content)
else:
    # Save it now over the translation
    english.save(sys.argv[1])
