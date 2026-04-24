"""UC-01: @mention parser unit tests."""
import pytest
from app.utils.mention_parser import parse_mention, get_mentioned_raw


class TestParseMention:
    """UC-01: @mention parser unit tests."""

    # -- Happy path --
    def test_english_start(self):
        assert parse_mention("@deema check leave") == ("deema", "check leave")

    def test_english_middle(self):
        assert parse_mention("hey @mohammad schedule interview") == ("mohammad", "hey schedule interview")

    def test_english_end(self):
        assert parse_mention("check leave @waleed") == ("waleed", "check leave")

    def test_case_insensitive(self):
        assert parse_mention("@DEEMA help")[0] == "deema"
        assert parse_mention("@Ahmad report")[0] == "ahmad"

    # -- Arabic --
    def test_arabic_name(self):
        assert parse_mention("@\u062f\u064a\u0645\u0629 \u0643\u0645 \u0631\u0635\u064a\u062f \u0625\u062c\u0627\u0632\u0627\u062a\u064a\u061f") == ("deema", "\u0643\u0645 \u0631\u0635\u064a\u062f \u0625\u062c\u0627\u0632\u0627\u062a\u064a\u061f")

    def test_arabic_with_diacritics(self):
        assert parse_mention("@\u0623\u064e\u062d\u0652\u0645\u064e\u062f analytics") == ("ahmad", "analytics")

    # -- Aliases --
    def test_alias_ahmed(self):
        assert parse_mention("@ahmed report")[0] == "ahmad"

    def test_alias_sarah(self):
        assert parse_mention("@sarah build agent")[0] == "yara"

    def test_alias_norah(self):
        assert parse_mention("@\u0646\u0648\u0631\u0629 \u062a\u0642\u0631\u064a\u0631")[0] == "ahmad"

    # -- Edge cases --
    def test_no_mention(self):
        assert parse_mention("just a normal message") == (None, "just a normal message")

    def test_unknown_agent(self):
        assert parse_mention("@unknown help") == (None, "@unknown help")

    def test_email_not_matched(self):
        assert parse_mention("email user@deema.com")[0] is None

    def test_multiple_mentions_first_wins(self):
        name, cleaned = parse_mention("@deema then ask @ahmad")
        assert name == "deema"
        assert "@ahmad" in cleaned

    def test_empty_after_mention(self):
        assert parse_mention("@deema") == ("deema", "")

    def test_whitespace_collapse(self):
        _, cleaned = parse_mention("hello  @deema  world")
        assert "  " not in cleaned

    def test_dept_agent(self):
        name, cleaned = parse_mention("@dept:550e8400 help with IT")
        assert name == "dept:550e8400"
        assert cleaned == "help with IT"

    # -- get_mentioned_raw --
    def test_raw_mention_found(self):
        assert get_mentioned_raw("@deema help") == "@deema"

    def test_raw_mention_arabic(self):
        assert get_mentioned_raw("@\u0623\u062d\u0645\u062f report") == "@\u0623\u062d\u0645\u062f"

    def test_raw_mention_none(self):
        assert get_mentioned_raw("no mention") is None
