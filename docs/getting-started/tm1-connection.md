# TM1 Connection

OptimusPy uses TM1py to connect to TM1 / Planning Analytics. Connections live in `config/config.ini`, one section per instance, freely-named (the section name is what you reference as `instance` in cube configs and in the UI).

## INI file format

```ini
[tm1srv01]
address=localhost
port=12354
user=admin
password=apple
ssl=False

[planning_sample]
address=localhost
port=12354
user=Admin
password=YXBwbGU=
decode_b64=True
ssl=True
```

Each `[section]` is independent. Add as many instances as you like (DEV, UAT, PROD, regional models, etc.).

## On-premise (address / port)

```ini
[tm1srv01]
address=tm1.example.com
port=8010
user=admin
password=mypassword
ssl=true
async_requests_mode=true
```

| Parameter | Description |
|---|---|
| `address` | Hostname or IP of the TM1 server |
| `port` | TM1 REST API port (often 8010 / 12354 / 5021) |
| `user` | TM1 user name |
| `password` | Plaintext or base64-encoded password |
| `ssl` | `true` for HTTPS, `false` for HTTP |
| `async_requests_mode` | `true` recommended for long-running queries |

## IBM Cloud / Planning Analytics on Cloud

```ini
[paac_prod]
base_url=https://your-tenant.planning-analytics.cloud.ibm.com/tm1/api/TM1 PROD
user=automation_user
password=your_password
namespace=LDAP
ssl=true
verify=true
async_requests_mode=true
```

| Parameter | Description |
|---|---|
| `base_url` | Full PA-on-Cloud REST URL including the model name |
| `namespace` | Authentication namespace (commonly `LDAP`) |
| `verify` | `true` validates the TLS certificate (recommended) |

!!! tip "Spaces in model names"
    `base_url` may contain spaces (e.g., `…/tm1/api/TM1 PROD`). Do **not** URL-encode them, because `configparser` reads the value as-is.

## Encoded passwords (`decode_b64`)

To avoid storing plaintext passwords:

```bash
python -c "import base64; print(base64.b64encode(b'mypassword').decode())"
```

Set `password` to the encoded value and add `decode_b64=True`:

```ini
password=bXlwYXNzd29yZA==
decode_b64=True
```

!!! warning "Not encryption"
    Base64 is encoding, not encryption: anyone with the file can decode it. Use OS-level file permissions or a secrets manager for real protection.

## Common parameters

| Parameter | Default | Description |
|---|---|---|
| `session_context` | always `optimuspy` | Label that appears in `}StatsByActiveSession`. OptimusPy sets it itself, so a value in `config.ini` is ignored. |
| `async_requests_mode` | `false` | Recommended `true` for benchmarking large cubes |
| `connection_pool_size` | `10` | Connection pool size for parallel requests |

## Which config.ini is read

There are three ways to choose the file:

1. **`--config PATH`** on the command line, for one run: `optimuspy scan --instance tm1srv01 --config /path/to/shared/config.ini`, or `optimuspy ui --config ...`. If the file doesn't exist, OptimusPy prints `ERROR: config.ini not found: <path>` and exits with code 1 before it connects.
2. **A link from the Settings page.** On [Settings → TM1 Instances](../ui/settings-page.md#tm1-instances), give the path to a `config.ini`, or to the folder that holds one, and click **Link to this file**. OptimusPy then reads that file where it is, so edits made for [RushTI](https://github.com/cubewise-code/rushti) or your own scripts show up without a second copy.
3. **OptimusPy's own copy**, `config/config.ini` in the folder you run from (for the bundle, the executable's folder). Create it from `config/config.ini.example`, or fill it with **Copy into OptimusPy** on the Settings page, which copies a file byte for byte, comments included.

The first that applies wins: `--config`, then the link, then `config/config.ini`.

The link is saved in [`config/settings.ini`](settings.md), so it's shared by the UI and the CLI: once you link a file in Settings, `optimuspy optimize x.json` without `--config` reads it too. If the linked file goes missing, the CLI prints `ERROR: config.ini not found: <path> (linked from the UI's Settings page)` and exits with code 1. The UI still starts, and Settings reports the missing file so you can link another one or switch back to `config/config.ini`.

OptimusPy doesn't edit a `config.ini`; the only file it writes is the copy **Copy into OptimusPy** makes. You edit the file in a text editor, or in the tool it belongs to. The Settings page shows each instance's fields read-only and has **Test Connection**.

[Settings Page →](../ui/settings-page.md)
