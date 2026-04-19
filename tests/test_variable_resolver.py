from services.variable_resolver import VariableResolver


def test_generation_date_substitutes_passed_value():
    assert VariableResolver().resolve("{generation_date}", generation_date="2026-04-19") == "2026-04-19"


def test_version_number_substitutes_passed_value():
    assert VariableResolver().resolve("v{version_number}", version_number=3) == "v3"


def test_author_substitutes_passed_value():
    assert VariableResolver().resolve("by {author}", author="Jane Doe") == "by Jane Doe"


def test_missing_value_renders_literal_placeholder():
    assert VariableResolver().resolve("{generation_date} {version_number} {author}") \
        == "{generation_date} {version_number} {author}"


def test_unknown_placeholder_passes_through_literal():
    assert VariableResolver().resolve("{unknown_variable}") == "{unknown_variable}"


def test_multiple_occurrences_of_same_placeholder_all_resolve():
    assert VariableResolver().resolve(
        "{generation_date} and {generation_date}", generation_date="2026-04-19"
    ) == "2026-04-19 and 2026-04-19"


def test_empty_string_unchanged():
    assert VariableResolver().resolve("") == ""


def test_plain_text_without_placeholders_unchanged():
    assert VariableResolver().resolve("just plain text") == "just plain text"


def test_placeholder_embedded_in_surrounding_text():
    assert VariableResolver().resolve(
        "on {generation_date} the report was issued", generation_date="2026-04-19"
    ) == "on 2026-04-19 the report was issued"


def test_explicit_none_kwarg_renders_literal():
    assert VariableResolver().resolve("{version_number}", version_number=None) == "{version_number}"
