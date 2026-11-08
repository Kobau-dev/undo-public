import platform

import pytest

from undo import permissions


@pytest.fixture
def on_mac(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")


def test_lists_only_what_is_missing(on_mac, monkeypatch):
    monkeypatch.setattr(permissions, "CHECKS", {"A": lambda: True, "B": lambda: False})
    assert permissions.missing_permissions() == ["B"]


def test_a_check_that_fails_is_not_reported(on_mac, monkeypatch):
    def boom():
        raise OSError

    monkeypatch.setattr(permissions, "CHECKS", {"A": boom})
    assert permissions.missing_permissions() == []


def test_nothing_to_check_outside_macos(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert permissions.missing_permissions() == []
