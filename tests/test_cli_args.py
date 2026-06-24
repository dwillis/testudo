"""Tests for CLI argument wiring."""

import sys
from unittest.mock import patch
import cli


def test_workers_and_rate_flow_into_config():
    captured = {}

    class FakeScraper:
        def __init__(self, config):
            captured["config"] = config

        def scrape_department(self, department_id=None, term=None):
            pass

        def scrape_full(self, term=None):
            pass

        def print_stats(self):
            pass

    argv = ["prog", "--department", "CMSC", "--workers", "12", "--rate", "3.5"]
    with patch.object(sys, "argv", argv), \
         patch.object(cli, "TestudoScraper", FakeScraper):
        try:
            cli.main()
        except SystemExit:
            pass

    assert captured["config"].workers == 12
    assert captured["config"].requests_per_second == 3.5
