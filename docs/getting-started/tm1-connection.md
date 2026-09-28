# TM1 Connection

OptimusPy uses TM1py to connect to TM1 / Planning Analytics. Connections live in `config/config.ini` — one section per instance, freely-named (the section name is what you reference as `instance` in cube configs and in the UI).

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

Each `[section]` is independent. Add as many instances as you like — DEV, UAT, PROD, regional models, etc.

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
    `base_url` may contain spaces (e.g. `…/tm1/api/TM1 PROD`). Do **not** URL-encode them — `configparser` reads the value as-is.

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
    Base64 is encoding, not encryption — anyone with the file can decode it. Use OS-level file permissions or a secrets manager for real protection.

## Common parameters

| Parameter | Default | Description |
|---|---|---|
| `session_context` | `optimuspy` | Label that appears in `}StatsByActiveSession` |
| `async_requests_mode` | `false` | Recommended `true` for benchmarking large cubes |
| `connection_pool_size` | `10` | Connection pool size for parallel requests |

## Editing connections from the UI

You don't have to hand-edit `config.ini`. The **Settings → TM1 Instances** page provides full CRUD: add/remove fields, create/delete instances, and **Test Connection** before saving.

[Settings Page →](../ui/settings-page.md)

## Sharing config.ini across tools

If you already maintain a `config.ini` for another tm1py tool (e.g. [RushTI](https://github.com/cubewise-code/rushti)), you don't need a second copy for OptimusPy. Point OptimusPy at the shared file with `--config`:

```bash
optimuspy scan --instance tm1srv01 --config /path/to/shared/config.ini
python -m optimuspy.ui --config /path/to/shared/config.ini
```

OptimusPy then consumes that file **read-only** — it never writes to it, so both tools can safely read the same credentials without stepping on each other. Manage the file's contents (add instances, rotate passwords) in whichever tool owns it; in OptimusPy's UI the Settings page reflects this with a read-only banner and disabled edit controls (Test Connection still works).

This only applies when `--config` is passed explicitly. Without the flag, OptimusPy falls back to its own default `config/config.ini`, which remains fully editable from the Settings page.

If the file passed to `--config` does not exist, OptimusPy prints `ERROR: config.ini not found: <path>` and exits with code 1 before it connects.
