from datetime import datetime

from services.variable_resolver import VariableResolver


def test_generation_date_resolves_to_today_iso():
    resolver = VariableResolver()
    assert resolver.resolve("{generation_date}") == datetime.utcnow().strftime("%Y-%m-%d")


def test_unknown_placeholder_passes_through_literal():
    resolver = VariableResolver()
    assert resolver.resolve("{unknown_variable}") == "{unknown_variable}"


def test_multiple_placeholders_all_resolve():
    resolver = VariableResolver()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert resolver.resolve("{generation_date} and {generation_date}") == f"{today} and {today}"


def test_empty_string_unchanged():
    resolver = VariableResolver()
    assert resolver.resolve("") == ""


def test_plain_text_without_placeholders_unchanged():
    resolver = VariableResolver()
    assert resolver.resolve("just plain text with no braces") == "just plain text with no braces"


def test_placeholder_embedded_in_surrounding_text():
    resolver = VariableResolver()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    assert resolver.resolve("on {generation_date} the report was issued") == f"on {today} the report was issued"
