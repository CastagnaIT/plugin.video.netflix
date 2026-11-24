# Device-bound session (optional)

On some Android devices the website login cannot authenticate MSL requests:
the NetflixId cookies are minted for the website ESN while the MSL sender
entity is the device ESN, and the server answers 205032 "User authentication
data does not match entity identity". The USER_ID_TOKEN branch needs a user
token, and no login flow in the add-on mints one for that device identity.

This feature lets a user provision a device-bound session instead. Create
`device_session.json` in the add-on profile directory
(`userdata/addon_data/plugin.video.netflix/`):

```json
{
  "esn": "<NFANDROID2 device ESN>",
  "mastertoken": { "tokendata": "...", "signature": "..." },
  "useridtoken": { "tokendata": "...", "signature": "..." }
}
```

When the file is present and valid:

- the ESN is pinned to the value in the file and is never regenerated;
- MSL requests authenticate with `userauthdata` `USER_ID_TOKEN` carrying the
  mastertoken and useridtoken pair, the same shape the platform client uses.

Without the file nothing changes. The tokens and the ESN must belong together;
removing the file returns the add-on to the normal login path.

## Trade-off: the ESN pin disables the 20-hour rotation

The add-on normally regenerates the last part of the ESN every 20 hours because
Netflix limits an ESN that stays in use for longer than about 20 hours to 540p.
A pinned device session cannot rotate its ESN, so that cap returns: playback
keeps working, but the ladder drops. Refresh the session (and the ESN it is
bound to) when full resolution matters.
