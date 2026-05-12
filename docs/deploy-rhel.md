# OptimusPy — RHEL Deployment Guide

This guide explains how to install and update **OptimusPy** on a Red Hat
Enterprise Linux server (RHEL 8 or 9), and how to trigger updates
automatically from a TM1 TurboIntegrator (TI) process via
`ExecuteCommand`.

The deployment uses a small Bash helper, `deploy-optimuspy.sh`, which
downloads the latest published build from GitHub, installs it in place
next to itself, and writes a timestamped log of every action.

---

## 1. What gets installed

After deployment, the install directory contains:

```
<install-dir>/
├── deploy-optimuspy.sh      ← deployment script (left alone after install)
├── config.ini               ← your configuration (left alone after install)
├── optimuspy                ← the OptimusPy executable
├── _internal/               ← bundled libraries and Python runtime
├── optimuspy-deploy.log     ← deployment log (appended to on each run)
└── *.bak.<timestamp>        ← previous versions, kept for rollback
```

**Only `optimuspy` and `_internal/` are ever replaced.** Your
`config.ini`, the deployment script, the log file, and any other files
in the directory are never touched.

The 3 most recent backups are kept automatically; older ones are
pruned. This is configurable.

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| RHEL 8 or 9 (x86_64) | Built against glibc 2.28; works on RHEL 8+ |
| `bash`, `curl`, `tar` | Standard on every RHEL install |
| Outbound HTTPS to `github.com` | Or use the air-gapped option (§7) |
| A user account with write access to the install directory | Typically the TM1 service account |

**No root access required.** OptimusPy installs entirely inside a
directory the TM1 service account owns.

---

## 3. One-time initial setup

Run these steps **once**, signed in as the user that the TM1 server
runs under (typically `tm1svc` or similar — your TM1 administrator
will know).

```bash
# 1. Choose an install directory and create it
mkdir -p ~/optimuspy
cd ~/optimuspy

# 2. Download the deployment script
curl -fSL -o deploy-optimuspy.sh \
  https://raw.githubusercontent.com/cubewise-code/optimus-py/master/scripts/deploy-optimuspy.sh

# 3. Make it executable
chmod +x deploy-optimuspy.sh

# 4. Place your config.ini in the same directory
#    (copy from your existing setup, or create a new one)
#    Example: scp config.ini tm1svc@rhel-host:~/optimuspy/

# 5. Run the first install
./deploy-optimuspy.sh
```

The first run downloads the latest published build and installs it
into `~/optimuspy/`. Check the log to confirm:

```bash
tail -n 50 ~/optimuspy/optimuspy-deploy.log
```

You should see `deploy complete: /home/tm1svc/optimuspy` near the end.

---

## 4. Verifying the install

Run the binary directly to confirm it starts cleanly:

```bash
~/optimuspy/optimuspy --help
```

If you see usage information, the install is good. If you see an
error such as `error while loading shared libraries`, see §9
Troubleshooting.

---

## 5. Updating from TM1 (TurboIntegrator)

Once the initial setup is in place, you can re-deploy the latest build
at any time from a TI process. The script logs everything to
`optimuspy-deploy.log` because TM1's `ExecuteCommand` does not return
stdout or stderr to the TI script.

**TI prolog/epilog example — install the latest build:**

```
ExecuteCommand( '/home/tm1svc/optimuspy/deploy-optimuspy.sh', 1 );
```

The trailing `1` (`Wait`) makes the TI step block until the script
finishes. After it completes, you can read the log with another TI
step or out of band.

**Pin a specific build (recommended for production):**

```
ExecuteCommand( 'env RELEASE_TAG=build-2af8147 /home/tm1svc/optimuspy/deploy-optimuspy.sh', 1 );
```

Replace `build-2af8147` with the tag of the build you want. Tags are
published at:

> https://github.com/cubewise-code/optimus-py/releases

Pinning is recommended for production so updates are deliberate.
"latest" can change at any time.

---

## 6. Updating manually

If you prefer to update from the command line instead of TM1:

```bash
cd ~/optimuspy
./deploy-optimuspy.sh                              # always-latest
RELEASE_TAG=build-2af8147 ./deploy-optimuspy.sh    # pinned version
```

---

## 7. Air-gapped deployment (no internet from the RHEL host)

If the RHEL host cannot reach `github.com`, transfer the release
archive manually:

1. On any machine with internet access, download the release archive:
   ```
   https://github.com/cubewise-code/optimus-py/releases/download/build-<sha>/optimuspy-linux.tar.gz
   ```
2. Copy it to the RHEL host, e.g.:
   ```bash
   scp optimuspy-linux.tar.gz tm1svc@rhel-host:~/optimuspy/
   ```
3. Run the deployment script with `LOCAL_TARBALL`:
   ```bash
   cd ~/optimuspy
   LOCAL_TARBALL=~/optimuspy/optimuspy-linux.tar.gz ./deploy-optimuspy.sh
   ```

   Or from a TI process:
   ```
   ExecuteCommand( 'env LOCAL_TARBALL=/home/tm1svc/optimuspy/optimuspy-linux.tar.gz /home/tm1svc/optimuspy/deploy-optimuspy.sh', 1 );
   ```

---

## 8. Rollback to the previous version

Every deployment backs up the previous binary and `_internal/`
directory next to themselves with a timestamp suffix. To roll back:

```bash
cd ~/optimuspy

# List available backups (newest first)
ls -1dt optimuspy.bak.* _internal.bak.*

# Pick a timestamp, then restore both items together.
# Replace <ts> with the timestamp from the listing above.
TS=<ts>

# Move current aside (in case you want to keep it)
mv optimuspy        optimuspy.failed.$(date -u +%Y%m%d-%H%M%S)
mv _internal        _internal.failed.$(date -u +%Y%m%d-%H%M%S)

# Restore from backup
mv optimuspy.bak.$TS  optimuspy
mv _internal.bak.$TS  _internal

# Verify
./optimuspy --help
```

---

## 9. Troubleshooting

The single source of truth is the log file:

```
~/optimuspy/optimuspy-deploy.log
```

Each entry is timestamped (UTC). Failures are logged with the line
number and the exact command that failed.

### Common issues

**`download failed from https://github.com/...`**
The host cannot reach GitHub. Check outbound HTTPS connectivity, or
use the air-gapped flow (§7).

**`INSTALL_DIR is not writable by <user>`**
The user running the script does not have write access to the install
directory. Confirm ownership:
```bash
ls -ld ~/optimuspy
```
The directory should be owned by the user that the TM1 server runs as.

**`error while loading shared libraries: libXXX.so.N`**
The binary cannot find a system library. This is rare on standard
RHEL but can happen on a stripped-down install. Identify the missing
library and install the corresponding RPM (often `zlib`, `glibc`, or
`libstdc++`).

**`binary failed to load shared libraries — aborting deploy`**
The script detected a broken binary during the smoke test and refused
to replace your working install. Check the smoke test output above
this line in the log to see the exact loader error.

**TI process completes but nothing changed**
TM1's `ExecuteCommand` does not surface failures to the TI engine.
Always check `optimuspy-deploy.log` after a TI-triggered deployment.

---

## 10. Configuration reference

All settings can be overridden via environment variables when
invoking the script:

| Variable | Default | Purpose |
|---|---|---|
| `RELEASE_TAG` | `latest` | GitHub release tag to install |
| `INSTALL_DIR` | the script's own directory | Where to install |
| `LOG_FILE` | `$INSTALL_DIR/optimuspy-deploy.log` | Log file path |
| `LOCAL_TARBALL` | (unset) | Path to a pre-staged `.tar.gz`; skips download |
| `KEEP_BACKUPS` | `3` | How many old backup sets to retain |
| `GITHUB_REPO` | `cubewise-code/optimus-py` | Source repository |

Examples:

```bash
# Install into a specific directory
INSTALL_DIR=/opt/optimuspy ./deploy-optimuspy.sh

# Keep more rollback history
KEEP_BACKUPS=10 ./deploy-optimuspy.sh

# Send the log to a central location
LOG_FILE=/var/log/optimuspy/deploy.log ./deploy-optimuspy.sh
```

---

## 11. Support

When reporting an issue, please include:

1. The contents of `~/optimuspy/optimuspy-deploy.log` (last ~100
   lines is usually enough).
2. The output of:
   ```bash
   cat /etc/redhat-release
   uname -a
   ls -la ~/optimuspy/
   ```
3. The release tag you were trying to install.
