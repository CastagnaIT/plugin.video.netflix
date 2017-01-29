import os
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDONVERSION = ADDON.getAddonInfo('version')
ADDONNAME = ADDON.getAddonInfo('name')
ADDONPATH = ADDON.getAddonInfo('path').decode('utf-8')
ADDONPROFILE = xbmc.translatePath( ADDON.getAddonInfo('profile') ).decode('utf-8')
ADDONUSERDATA = xbmc.translatePath("special://profile/addon_data/service.msl").decode('utf-8') + "/"
ICON = ADDON.getAddonInfo('icon')

def log(txt):
    if isinstance (txt,str):
        txt = txt.decode("utf-8")
    message = u'%s: %s' % ("service.msl", txt)
    xbmc.log(msg=message.encode("utf-8"), level=xbmc.LOGDEBUG)
