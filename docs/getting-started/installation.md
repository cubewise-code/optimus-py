# Installation

!!! info "Requirements"
    - Network access to your TM1 / Planning Analytics server
    - For the web UI: a modern browser (Chrome, Firefox, Edge, Safari)
    - For an install from source: Python 3.9 or newer

## From source

```bash
git clone https://github.com/cubewise-code/optimus-py.git
cd optimus-py
pip install -e .
```

This installs the dependencies (TM1py 2.3.0 or later, mdxpy, pandas, XlsxWriter and configparser). `-e` installs in editable mode, so code changes take effect without reinstalling. The `optimuspy` and `python -m optimuspy` commands both become available.

Verify the install:

```bash
optimuspy --help
```

## Prebuilt bundles

Use a bundle when you cannot install Python (locked-down servers, kiosk environments, etc.). The **Build Executable** workflow builds a Windows and a Linux bundle. Each unpacks to an `optimuspy/` folder holding the executable, `config/config.ini.example`, `config/settings.ini.example` (see [Settings File](settings.md)) and `samples/` (example cube configs).

### Windows

1. Open the [Actions tab](https://github.com/cubewise-code/optimus-py/actions) of the repository.
2. Click the most recent successful **Build Executable** run.
3. Scroll to the **Artifacts** section and download `optimuspy-windows`.
4. Unzip it. The `optimuspy/` folder holds `optimuspy.exe`, `config/config.ini.example`, `config/settings.ini.example` and `samples/` (example cube configs).
5. Copy `config/config.ini.example` to `config/config.ini` and fill in your TM1 instances, or link the `config.ini` you already have under **Settings**. Double-click `optimuspy.exe` to open the web UI.

Builds from `master` also publish the same bundle as `optimuspy-windows.zip` on the [Releases page](https://github.com/cubewise-code/optimus-py/releases).

### Linux

1. Download the bundle for your machine's processor from the [Releases page](https://github.com/cubewise-code/optimus-py/releases). `uname -m` tells you which one:
    - `x86_64`: `optimuspy-linux.tar.gz`;
    - `aarch64`: `optimuspy-linux-arm64.tar.gz`, for ARM servers and for Linux VMs on an Apple Silicon Mac.

    The x86-64 bundle doesn't run on `aarch64`, even where the system can emulate x86-64: it stops at startup with `Failed to create parent directory structure` or a segmentation fault.
2. Unpack it and start the executable:

    ```bash
    tar -xzf optimuspy-linux.tar.gz   # or optimuspy-linux-arm64.tar.gz
    cd optimuspy
    ./optimuspy
    ```

    With no arguments it opens the web UI. The UI listens on `127.0.0.1` only, so open it in a browser on the same machine. Copy `config/config.ini.example` to `config/config.ini` and fill it in, or link the `config.ini` you already have under **Settings**; the command line reads the same file, for example `./optimuspy scan --instance <name>`.

The same bundles are kept as the `optimuspy-linux` and `optimuspy-linux-arm64` artifacts of each **Build Executable** run on the [Actions tab](https://github.com/cubewise-code/optimus-py/actions). GitHub delivers an artifact as a zip, which does not keep the executable bit: after unzipping, run `chmod +x optimuspy/optimuspy`.

## Next step

Configure your first TM1 connection: [TM1 Connection →](tm1-connection.md)
