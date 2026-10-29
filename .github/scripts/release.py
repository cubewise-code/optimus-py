"""Release helpers for the Build Executable workflow.

The workflow calls this script to decide whether a merge to master releases,
which version it releases, to write that version into the code, and to take the
release notes from CHANGELOG.md. Keeping the decisions here, rather than in the
workflow's shell steps, lets the test suite cover them.

    python .github/scripts/release.py current
    python .github/scripts/release.py plan --labels "release:minor,bug" --tags "$(git tag -l)"
    python .github/scripts/release.py set-version 2.1.0
    python .github/scripts/release.py notes 2.1.0 --repo cubewise-code/optimus-py
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Each file that carries the version, and the line that holds it.
VERSION_FILES = {
    "pyproject.toml": re.compile(r'^version = "([^"]*)"', re.MULTILINE),
    "src/optimuspy/__init__.py": re.compile(r'^__version__ = "([^"]*)"', re.MULTILINE),
}

# PR label -> version part it bumps, highest first.
RELEASE_LABELS = {
    "release:major": "major",
    "release:minor": "minor",
    "release:patch": "patch",
}

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse_version(version):
    match = SEMVER.match(version)
    if not match:
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {version!r}")
    return tuple(int(part) for part in match.groups())


def current_version(root=ROOT):
    """The version in the code. Every version file must agree."""
    found = {}
    for name, pattern in VERSION_FILES.items():
        match = pattern.search((root / name).read_text(encoding="utf-8"))
        if not match:
            raise ValueError(f"no version line in {name}")
        found[name] = match.group(1)
    versions = set(found.values())
    if len(versions) != 1:
        detail = ", ".join(f"{name} has {version}" for name, version in found.items())
        raise ValueError(f"the version files disagree: {detail}")
    version = versions.pop()
    parse_version(version)
    return version


def bump_part(labels):
    """The part the PR labels ask to bump, or None when no release label is set."""
    for label, part in RELEASE_LABELS.items():
        if label in labels:
            return part
    return None


def bump(version, part):
    major, minor, patch = parse_version(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown version part: {part!r}")


def latest_released(tags):
    """The highest version among the vMAJOR.MINOR.PATCH tags, or None."""
    versions = [tag[1:] for tag in tags if tag.startswith("v") and SEMVER.match(tag[1:])]
    return max(versions, key=parse_version, default=None)


def plan(labels, tags, version):
    """What a merge with these labels releases.

    A version in the code that is newer than every release is released as it
    stands, so a version set by hand (2.0.0, say) is not bumped past. Otherwise
    the labelled part is bumped from the newest of the code's version and the
    released ones, so a merge whose code predates the last release still
    bumps past that release.
    """
    part = bump_part(labels)
    if part is None:
        return {"release": "false", "version": version, "tag": "", "bump": ""}
    released = latest_released(tags)
    if released is None or parse_version(version) > parse_version(released):
        new_version, how = version, "none"
    else:
        new_version, how = bump(released, part), part
    return {"release": "true", "version": new_version, "tag": f"v{new_version}", "bump": how}


def set_version(version, root=ROOT):
    parse_version(version)
    for name, pattern in VERSION_FILES.items():
        path = root / name
        text = path.read_text(encoding="utf-8")
        line = pattern.search(text).group(0)
        prefix = line[: line.index('"')]
        path.write_text(text.replace(line, f'{prefix}"{version}"', 1), encoding="utf-8")


# A Markdown link target that is a path inside the repository.
_RELATIVE_LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)")


def release_notes(version, repo, root=ROOT):
    """The CHANGELOG.md section for this version, or "" when it has none.

    The section runs from its `## <version>` heading to the next `## ` heading.
    Links to files in the repository are pointed at the release's tag, because
    a release page does not resolve relative links.
    """
    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        return ""
    heading = re.compile(rf"^## \[?v?{re.escape(version)}\]?(?:\s|$)")
    lines, taking = [], False
    for line in changelog.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            if taking:
                break
            taking = bool(heading.match(line))
            continue
        if taking:
            lines.append(line)
    body = "\n".join(lines).strip()
    base = f"https://github.com/{repo}/blob/v{version}/"
    return _RELATIVE_LINK.sub(lambda m: f"]({base}{m.group(1).removeprefix('./')})", body)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("current", help="print the version in the code")
    plan_cmd = commands.add_parser("plan", help="print key=value lines for $GITHUB_OUTPUT")
    plan_cmd.add_argument("--labels", default="", help="the merged PR's labels, comma-separated")
    plan_cmd.add_argument("--tags", default="", help="the repository's tags, one per line")
    set_cmd = commands.add_parser("set-version", help="write a version into every version file")
    set_cmd.add_argument("version")
    notes_cmd = commands.add_parser("notes", help="print the CHANGELOG.md section for a version")
    notes_cmd.add_argument("version")
    notes_cmd.add_argument("--repo", required=True, help="owner/name, for links to files")
    args = parser.parse_args(argv)

    try:
        if args.command == "current":
            print(current_version())
        elif args.command == "plan":
            labels = {label.strip() for label in args.labels.split(",") if label.strip()}
            tags = {tag.strip() for tag in args.tags.splitlines() if tag.strip()}
            for key, value in plan(labels, tags, current_version()).items():
                print(f"{key}={value}")
        elif args.command == "set-version":
            set_version(args.version)
        elif args.command == "notes":
            print(release_notes(args.version, args.repo))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
