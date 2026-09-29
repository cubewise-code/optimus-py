# Contributing to OptimusPy

## Development

With Python 3.9 or later, clone the repository and install it with its development tools:

```bash
pip install -e ".[dev]"
python -m pytest -q
```

The default test run needs no TM1 server. The live tests are opt-in: `python -m pytest -m live --instance tm1srv01`.

Build the documentation into a temporary folder, because `./site` holds the landing page:

```bash
python -m mkdocs build --strict --site-dir "$(mktemp -d)/site"
```

## Pull requests

Open pull requests against `master`. A pull request runs the tests and, when it changes the code, one Linux build of the executable.

## Releases

Versions follow [semantic versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. A maintainer picks the release when merging, with one label on the pull request:

| Label | Bump | Use it for |
|---|---|---|
| `release:patch` | 2.0.0 → 2.0.1 | Bug fixes and small improvements |
| `release:minor` | 2.0.0 → 2.1.0 | New features that break nothing |
| `release:major` | 2.0.0 → 3.0.0 | A cube config, command or setting that worked before stops working |

With several labels, the highest one counts.

When a labelled pull request is merged to `master` and the tests pass, the **Build Executable** workflow:

1. sets the new version in `pyproject.toml` and `src/optimuspy/__init__.py`, commits it to `master` and tags it `vX.Y.Z`;
2. builds the Windows, Linux x86-64 and Linux arm64 bundles from that tag, and runs each executable before keeping it;
3. creates the release `vX.Y.Z` with the three bundles. Its notes are the `## X.Y.Z` section of `CHANGELOG.md`, or GitHub's generated notes when there is none, so add that section in the same pull request.

A version in the code that is newer than every release is released as it stands: set `2.1.0` by hand, apply any release label, and the release is `v2.1.0`.

**No label, no new version.** A merge to `master` without a release label still builds the three bundles, and they replace the ones on the latest release. Each bundle holds a `BUILD_INFO.txt` with its version and the commit it was built from, so a download can always be traced to its code.

A merge that changes only the documentation or the landing page runs neither the tests nor the build, so it neither releases nor rebuilds the bundles, whatever its label.

Releases are published only from `cubewise-code/optimus-py`. A fork builds the bundles and keeps them as workflow artifacts. To try the whole release flow on a fork, set the repository variable `RELEASE_REPOSITORY` to the fork's `owner/name`.
