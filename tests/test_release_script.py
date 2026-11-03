"""The release decisions made by .github/scripts/release.py."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "release.py"
_spec = importlib.util.spec_from_file_location("release_script", SCRIPT)
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)

REPO = "cubewise-code/optimus-py"


def make_repo(tmp_path, pyproject="2.0.0", init="2.0.0", changelog=None):
    (tmp_path / "src" / "optimuspy").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "optimuspy"\nversion = "{pyproject}"\n\n[tool.black]\ntarget-version = ["py39"]\n'
    )
    (tmp_path / "src" / "optimuspy" / "__init__.py").write_text(
        f'"""OptimusPy."""\n\n__version__ = "{init}"\n'
    )
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog)
    return tmp_path


def test_the_repository_version_files_agree():
    assert release.parse_version(release.current_version())


def test_current_version_reads_both_files(tmp_path):
    assert release.current_version(make_repo(tmp_path)) == "2.0.0"


def test_current_version_rejects_files_that_disagree(tmp_path):
    with pytest.raises(ValueError, match="disagree"):
        release.current_version(make_repo(tmp_path, init="2.0.1"))


def test_current_version_rejects_a_version_that_is_not_semver(tmp_path):
    with pytest.raises(ValueError, match="MAJOR.MINOR.PATCH"):
        release.current_version(make_repo(tmp_path, pyproject="2.0", init="2.0"))


@pytest.mark.parametrize(
    "part, expected",
    [("patch", "2.3.5"), ("minor", "2.4.0"), ("major", "3.0.0")],
)
def test_bump(part, expected):
    assert release.bump("2.3.4", part) == expected


def test_the_highest_release_label_wins():
    assert release.bump_part({"release:patch", "release:major", "bug"}) == "major"
    assert release.bump_part({"release:minor", "release:patch"}) == "minor"
    assert release.bump_part({"bug", "documentation"}) is None


def test_no_release_label_means_no_release():
    assert release.plan({"bug"}, {"v2.0.0"}, "2.0.0") == {
        "release": "false", "version": "2.0.0", "tag": "", "bump": "",
    }


def test_a_labelled_merge_bumps_a_released_version():
    assert release.plan({"release:minor"}, {"v2.0.0", "2.0"}, "2.0.0") == {
        "release": "true", "version": "2.1.0", "tag": "v2.1.0", "bump": "minor",
    }


def test_a_version_without_a_tag_is_released_as_it_stands():
    # A 2021 "2.0" tag is not the v2.0.0 tag.
    assert release.plan({"release:major"}, {"2.0", "build-2e56231"}, "2.0.0") == {
        "release": "true", "version": "2.0.0", "tag": "v2.0.0", "bump": "none",
    }


def test_a_merge_whose_code_predates_the_last_release_bumps_past_it():
    # 2.1.0 was released while this merge, still at 2.0.0, waited its turn.
    assert release.plan({"release:patch"}, {"v2.0.0", "v2.1.0"}, "2.0.0")["version"] == "2.1.1"


def test_latest_released_ignores_tags_that_are_not_versions():
    assert release.latest_released({"2.0", "latest", "build-2e56231", "v2.10.0", "v2.9.1"}) == "2.10.0"
    assert release.latest_released({"2.0", "latest"}) is None


def test_set_version_rewrites_only_the_version_lines(tmp_path):
    root = make_repo(tmp_path)
    release.set_version("2.1.0", root)
    assert release.current_version(root) == "2.1.0"
    pyproject = (root / "pyproject.toml").read_text()
    assert 'target-version = ["py39"]' in pyproject
    assert pyproject.count("2.1.0") == 1


def test_set_version_rejects_a_version_that_is_not_semver(tmp_path):
    with pytest.raises(ValueError):
        release.set_version("2.1", make_repo(tmp_path))


CHANGELOG = """# Changelog

## 2.1.0 (2026-11-02)

Sync Order learns a dry run. See [Sync Order](docs/modes/sync-order.md) and [the site](https://example.org/x).

### Fixed

- A [fix](./docs/a.md#part), in [this section](#fixed).

## 2.0.0

The 2.0.0 notes.
"""


def test_release_notes_take_the_version_section(tmp_path):
    notes = release.release_notes("2.1.0", REPO, make_repo(tmp_path, changelog=CHANGELOG))
    assert notes.startswith("Sync Order learns a dry run.")
    assert "### Fixed" in notes
    assert "2.0.0 notes" not in notes


def test_release_notes_point_repository_links_at_the_tag(tmp_path):
    notes = release.release_notes("2.1.0", REPO, make_repo(tmp_path, changelog=CHANGELOG))
    base = f"https://github.com/{REPO}/blob/v2.1.0/"
    assert f"[Sync Order]({base}docs/modes/sync-order.md)" in notes
    assert f"[fix]({base}docs/a.md#part)" in notes
    assert "[the site](https://example.org/x)" in notes
    assert "[this section](#fixed)" in notes


def test_release_notes_for_the_last_section(tmp_path):
    notes = release.release_notes("2.0.0", REPO, make_repo(tmp_path, changelog=CHANGELOG))
    assert notes == "The 2.0.0 notes."


def test_release_notes_are_empty_without_a_section(tmp_path):
    assert release.release_notes("2.0.1", REPO, make_repo(tmp_path, changelog=CHANGELOG)) == ""
    assert release.release_notes("2.0.1", REPO, make_repo(tmp_path / "bare")) == ""


def test_release_notes_for_the_repository_changelog():
    assert release.release_notes("2.0.0", REPO).startswith("OptimusPy finds a better storage dimension order")
