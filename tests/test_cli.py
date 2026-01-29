from __future__ import annotations

import pytest

from python_starter.config import get_bot_token, get_settings


def test_get_bot_token_requires_env(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.setenv("OWNER_ID", "1")
    with pytest.raises(RuntimeError):
        get_bot_token()


def test_get_bot_token_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("OWNER_ID", "1")
    assert get_bot_token() == "123:ABC"


def test_get_settings_parses_admin_ids(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("OWNER_ID", "10")
    monkeypatch.setenv("ADMIN_IDS", "11, 12")
    s = get_settings()
    assert s.owner_id == 10
    assert 10 in s.admin_ids
    assert 11 in s.admin_ids
    assert 12 in s.admin_ids
