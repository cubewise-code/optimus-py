# Settings File

`config/settings.ini` holds the settings of one OptimusPy installation: which `config.ini` to read, where the UI saves files, and how the UI starts. It sits next to `config.ini` and follows the same pattern.

The file is optional. Every setting has a default in the code, and a missing file or a missing key means the default. OptimusPy ships `config/settings.ini.example`, never a live `settings.ini`, so unpacking a new version over an old one keeps your settings.

## The keys

All keys go in one `[optimuspy]` section:

```ini
[optimuspy]
ui_port = 9000
open_browser = false
```

| Key | Default | What it sets |
|---|---|---|
| `config_ini` | unset, which means `config/config.ini` | The `config.ini` the CLI and the UI read when `--config` isn't given. The [Settings page](../ui/settings-page.md#tm1-instances) sets it when you link a file. |
| `cube_configs_dir` | `cube-configs` | The folder the Optimize page saves cube configs to. |
| `exports_dir` | `exports` | The folder Sync Order's *Export to Folder* writes to. |
| `ui_port` | `8765` | The port the web UI listens on, from 1 to 65535. |
| `open_browser` | `true` | Whether starting the web UI opens a browser tab. |

A flag always wins over the file: `--config` over `config_ini`, and `--port` over `ui_port`.

An invalid value, such as a `ui_port` that isn't a port, is logged as a warning and the default is used. A file that can't be parsed is ignored in the same way, so a broken settings file never stops the CLI or the UI.

## Editing it

To change a setting by hand, copy `config/settings.ini.example` to `config/settings.ini` and uncomment the key. The example lists every key at its default, with a line explaining it.

When the UI changes a setting, it rewrites `config/settings.ini` with only the keys that differ from the default. Python's INI writer drops comments, so any comments you add are lost at that point; the explanations stay in the `.example` file.

`config/settings.ini` is relative to the folder you run from, like `config/config.ini`. For the bundle, that's the executable's folder.
