# Netflix Plugin for Kodi (plugin.video.netflix)

[![Kodi version](https://img.shields.io/badge/kodi%20versions-18--19-blue)](https://kodi.tv/)
[![GitHub release](https://img.shields.io/github/release/castagnait/plugin.video.netflix.svg)](https://github.com/castagnait/plugin.video.netflix/releases)
[![CI](https://github.com/castagnait/plugin.video.netflix/workflows/CI/badge.svg)](https://github.com/castagnait/plugin.video.netflix/actions?query=workflow:CI)
[![Code Climate - Maintainability](https://api.codeclimate.com/v1/badges/9fbe3ac732f86c05ff00/maintainability)](https://codeclimate.com/github/CastagnaIT/plugin.video.netflix/maintainability)
[![Codecov status](https://img.shields.io/codecov/c/github/castagnait/plugin.video.netflix/master)](https://codecov.io/gh/castagnait/plugin.video.netflix/branch/master)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Contributors](https://img.shields.io/github/contributors/castagnait/plugin.video.netflix.svg)](https://github.com/castagnait/plugin.video.netflix/graphs/contributors)

## Disclaimer

This plugin is not officially commissioned/supported by Netflix.
The trademark "Netflix" is registered by "Netflix, Inc."

## Features

- Access to multiple profiles
- Search Netflix including suggestions
- Netflix categories, recommendations, My List, continue watching and more
- Browse all movies and all TV shows Netflix style includes genres
- Browse trailers & more of TV shows and movies (by context menu)
- Can synchronize the watched status with Netflix service - [How works and limitations](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Sync-of-watched-status-with-Netflix)
- Rate TV shows and movies
- Add or remove to/from My List
- Export of TV shows & movies in Kodi local library
- Keep Netflix My List and Kodi local library in sync
- Automatic export of new seasons/episodes to Kodi local library when they become available on Netflix
- Share/Sync the Kodi local library with multiple devices that running Kodi with the same account (requires a MySQL server)
- Possibility of playback at 1080P and 4K (see high resolutions table)
- Support of hi-res audio Dolby Digital Plus and Dolby Digital Atmos (requires a premium account)
- Support of HDR / HDR10 only on capable android devices (requires a premium account)
- Support of Dolby Vision only on capable android devices (requires a premium account)
- Support integration with Up Next add-on (proposes to play the next episode automatically)

## Installation & Updates

**[How to install with automatic updates](https://github.com/CastagnaIT/plugin.video.netflix/wiki/How-install-the-addon)**

#### Quick download links

Install add-on via repository - provide automatic installation of updates:
* [CastagnaIT Repository for KODI 18.x LEIA - repository.castagnait-1.0.1.zip](https://github.com/castagnait/repository.castagnait/raw/master/repository.castagnait-1.0.1.zip)
* [CastagnaIT Repository for KODI 19.x MATRIX - repository.castagnait-1.0.0.zip](https://github.com/castagnait/repository.castagnait/raw/matrix/repository.castagnait-1.0.0.zip)

Install add-on manually - updates should always be installed manually:
* Daily builds - To get latest fixes https://bit.ly/citnfdailybuilds (not always published see dates)
* As Kodi file source, only for Kodi 18:<br/>
https://castagnait.github.io/repository.castagnait/ (url to add in the Kodi file manager)

## Reference table of high resolutions

This table explains compatibility of high resolutions between devices and operating systems. This may change over time based on updates made by netflix.

| System                 | 1080P    | 4K    | Video Decoding             |
| ---------------------- | -------- | ----- | -------------------------- |
| Windows                | ✔\*1     | ✖\*2  | Software                   |
| Linux (Android) \*5    | ✔\*1, \*3| ✔\*4  | Software \\ Hardware \*4   |
| Linux (OSMC-LibreELEC) | ✔\*1     | ✖\*2  | Software                   |
| Linux (Distros)        | ✔\*1     | ✖\*2  | Software                   |
| MacOS                  | ✔\*1     | ✖\*2  | Software                   |
| iOS / tvOS             | ✖        | ✖     | Not supported              |

\*1 ***With Software decoding 1080P is not guaranteed***.<br/>
\*2 Currently not available due to widevine limitations.<br/>
\*3 To to have a chance to have all the videos at 1080P you must meet \*4 requirements.<br/>
\*4 Hardware decoding and 4k are supported only to devices with Netflix certification, Widevine Security Level L1 and HDCP 2.2 hardware.<br/>
\*5 Some android devices do not work properly, this is due to restrictions implemented by netflix with devices with false certifications (often with some Chinese boxes) in rare cases even happened to not being able to play the videos.

[List of known and tested android devices for 1080P and 4K playback](https://github.com/CastagnaIT/plugin.video.netflix/wiki/List-of-1080P-4k-Android-tested-devices)

#### For video playback problems or 4K problems, BEFORE open an Issue:

- [Try read the FAQ on Wiki page for the common playback problems](https://github.com/CastagnaIT/plugin.video.netflix/wiki/FAQ-%28Audio%2C-Video%2C-Subtitle%2C-Other%29)
- [Try ask for help to the official Kodi forum](https://forum.kodi.tv/showthread.php?tid=329767)

## YOU NEED OTHER HELP? Read the Wiki page!

What you can find?

FAQs:

- [FAQ with how to for common problems with Audio, Video, Subtitles and other](https://github.com/CastagnaIT/plugin.video.netflix/wiki/FAQ-%28Audio%2C-Video%2C-Subtitle%2C-Other%29)
- [FAQ with how to for common errors](https://github.com/CastagnaIT/plugin.video.netflix/wiki/FAQ-%28Errors%29)

Some guides like:
- [How to export to Kodi library and use auto-sync](https://github.com/CastagnaIT/plugin.video.netflix/wiki/How-to-export-and-sync-tv-shows-and-movies-in-Kodi-library)
- [How to share the exported content in the library with multiple devices](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Use-library-exported-with-multiple-devices)
- [How works and limitations of the synchronisation of watched status with Netflix](https://github.com/CastagnaIT/plugin.video.netflix/wiki/Sync-of-watched-status-with-Netflix)

And much more...

[***Click here to open the Wiki page or click on Wiki button***](https://github.com/CastagnaIT/plugin.video.netflix/wiki)

## Notice for the use of auto-update and auto-sync with Netflix "My List" feature

AN INTENSIVE USE OF THIS FEATURES due to many exported tv shows MAY CAUSE A TEMPORARY BAN OF THE ACCOUNT that varies starting from 24/48 hours. Use at your own risk.

If it happens often, there is the possibility to exclude the auto update from the tv shows, by open context menu on a tv show and selecting `Exclude from auto update`.

## Something doesn't work

***Before open an issue please try read the Wiki pages or ask for help in the Kodi forum***

If something doesn't work for you:
1. Open add-on settings, go to in Expert page and change `Debug logging level` to `Verbose`
2. Enable the Debug log in your Kodi settings
3. Perform the actions that cause the error, so they are written in the log
4. Open a new github issue (of type *Problem report*) by following the instructions in the report

We can't help you if you don't provide detailed information (i.e. explanation and full debug log) on your issue.
Please also use a service like pastebin or better [Kodi paste](http://paste.kodi.tv) to provide logs and refrain from uploading them to where they'll be hidden behind an ad-wall or any other sketchy services.

When the problem will be solved, remember to disable the debug logging, to avoid unnecessary slowing down in your device.

**Why my Issue is labeled with ![Ignored rules](https://img.shields.io/badge/-Ignored%20rules-red) ?**

This happens when the guidelines for compiling the Issue post have not been followed. Therefore if the information will not be filled and or changed in the right way, the Issue post will be closed in the next days.


## Code of Conduct

[Contributor Code of Conduct](Code_of_Conduct.md)
By participating in this project you agree to abide by its terms.

## License

Licensed under The MIT License.
