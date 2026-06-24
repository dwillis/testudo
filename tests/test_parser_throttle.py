"""Tests for the parser's throttle hook."""

from unittest.mock import MagicMock
from testudo import ScraperConfig, TestudoParser


def test_throttle_uses_rate_limiter_when_present():
    limiter = MagicMock()
    parser = TestudoParser(ScraperConfig(request_delay=0.0), rate_limiter=limiter)
    parser._throttle()
    limiter.acquire.assert_called_once()


def test_throttle_falls_back_to_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr("testudo.parser.time.sleep", lambda s: calls.append(s))
    parser = TestudoParser(ScraperConfig(request_delay=0.7))
    parser._throttle()
    assert calls == [0.7]
