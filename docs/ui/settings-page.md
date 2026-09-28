# Settings Page

Manage TM1 connections, browser theme, local cache, and saved cube configs, all without touching `config.ini` by hand.

![Settings page with the TM1 Instances card showing the fields of an example instance](../assets/images/optimuspy/ui/settings-page.png)

## Appearance

Theme switcher: **System** (follows OS preference), **Light**, or **Dark**. Persists in `localStorage`.

## TM1 Instances

A tab per instance defined in `config.ini`. Each tab shows the instance's fields as editable rows.

### Read-only config.ini

If OptimusPy was launched with an explicit `--config PATH` (see [TM1 Connection](../getting-started/tm1-connection.md#sharing-configini-across-tools)), that file is treated as owned by another tool and the Settings page switches to read-only mode: a banner explains that the config is managed externally, and the create/edit/delete controls below are hidden. **Test Connection** still works, since it doesn't write to the file. The default `config/config.ini` (no `--config` flag) is never read-only.

### Editing fields

- Click any value to edit it.
- Click the **×** next to a field to delete that key from the section. This one takes effect immediately, without Save.
- Click **Add Field** to add a new key/value pair (freeform: type any TM1py-supported parameter name).
- Use **Update Password (write-only)** to change the password without exposing the current value.

Click **Save** to persist the edited values and the new password to `config.ini`.

![Instance field rows, each with a delete (×) button, and the Add Field button below](../assets/images/optimuspy/ui/settings-field-rows.png)

### Test Connection

Connects to the live TM1 server with the instance's saved `config.ini` fields (so Save first if you want to test an edit) and the password typed in **Update Password**, or else the one given in the Connect dialog. Returns the server name and cube count on success, or a clear error toast on failure.

![Test Connection success toast showing the server name and cube count](../assets/images/optimuspy/ui/settings-test-connection-toast.png)

### New Instance

Click **+ New Instance** above the tabs. A modal asks for the instance name (anything but empty or containing `]`; surrounding whitespace is trimmed). The new section appears as an empty tab where you add fields. If there is no `config.ini` yet (the executable ships without one), the first instance created here creates `config/config.ini`.

### Delete Instance

The red **Delete Instance** button at the bottom of each tab removes the section from `config.ini` after a confirmation modal. Permanent.

## Cache

Two caches are stored in your browser's `localStorage`:

| Cache | Key prefix | TTL |
|---|---|---|
| Scan results | `op-scan-` | 24 hours |
| Cube intelligence (dimension metadata) | `op-intel-` | 7 days |

Click **Clear Cache** to wipe both, plus the in-memory state. Use this after server-side changes (deleted string elements, renamed dimensions, fresh data load) to force a clean fetch.

## Saved Cube Configs

Lists every JSON config saved in `configs/` from the Optimize workflow. Each row shows the cube, then its instance, mode (`greedy` or `predefined`) and file name, with a trash button to delete it. Useful for cleaning up experiments.
