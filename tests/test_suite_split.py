"""The offline/live split is a property of the config, so it is checked there.

A live test that quietly runs in the default suite is not a failing test — it is
a test that tries to open a TCP connection on a CI runner that has no route to
the host, and then times out. These assertions keep the default selection honest
without needing a server to prove it.

Offline, no fake.
"""


def test_the_default_run_deselects_live_tests(pytestconfig):
    addopts = pytestconfig.getini("addopts")
    assert any("not live" in str(opt) for opt in addopts), (
        f"the default selection no longer excludes the live marker: {addopts}")


def test_the_live_marker_is_registered(pytestconfig):
    # Unregistered markers are a warning, not an error, so a typo'd
    # @pytest.mark.live would silently mark nothing and the test would run.
    markers = pytestconfig.getini("markers")
    assert any(str(m).startswith("live:") for m in markers), markers
