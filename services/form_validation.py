"""
Generic form-response validation.

Reads `form_fields.validation` JSON shapes and validates a {field_code: value}
response dict against them. The validator does not branch on form_code or
field_code identity — it loops over the field rows and applies generic rules.

Supported validation shapes:
    {"required": true}
    {"min": <number>}
    {"max": <number>}
    {"pattern": "<regex>"}
    {"in": [<values>]}

Multiple keys combine; "required" combines with any other rule.

Field-type discipline:
    text/textarea  -> string
    select         -> string, optionally constrained by `options`
    multiselect    -> list of strings, optionally constrained by `options`
    boolean        -> bool
    date           -> ISO 8601 string (only structural — caller sees raw)

Returns (errors_dict, normalised_responses). errors_dict is empty on success.
"""

import json
import re
from typing import Any, Iterable, Mapping


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False


def _coerce_value(field_type: str, raw: Any) -> Any:
    """Normalise the value to its field-type-shaped Python primitive.

    Booleans accept "true"/"false" string forms (form encoding).
    Multiselect accepts JSON-encoded strings.
    Returns the raw value unchanged when not normalisable here; downstream
    rule checks then catch the type mismatch.
    """
    if field_type == "boolean":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no", ""):
                return False
        return raw

    if field_type == "multiselect":
        if isinstance(raw, list):
            return raw
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped == "":
                return []
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return [stripped]
        return raw

    if field_type in ("text", "textarea", "select", "date"):
        if raw is None:
            return ""
        if not isinstance(raw, str):
            return str(raw)
        return raw

    return raw


def _check_rules(value: Any, rules: Mapping[str, Any], options: Iterable[str] | None, field_type: str) -> list[str]:
    errors: list[str] = []
    required = bool(rules.get("required"))

    if _is_blank(value):
        if required:
            errors.append("required")
        # No further rules apply to a blank value.
        return errors

    if "pattern" in rules and isinstance(value, str):
        try:
            if not re.fullmatch(rules["pattern"], value):
                errors.append("pattern")
        except re.error:
            errors.append("pattern_invalid")

    if "min" in rules:
        try:
            if float(value) < float(rules["min"]):
                errors.append("min")
        except (TypeError, ValueError):
            errors.append("min_not_numeric")

    if "max" in rules:
        try:
            if float(value) > float(rules["max"]):
                errors.append("max")
        except (TypeError, ValueError):
            errors.append("max_not_numeric")

    if "in" in rules:
        allowed = rules["in"]
        if value not in allowed:
            errors.append("not_in_allowed")

    # Field-type-specific consistency checks.
    if field_type == "select" and options:
        if value not in options:
            errors.append("not_in_options")
    if field_type == "multiselect":
        if not isinstance(value, list):
            errors.append("expected_list")
        elif options:
            for v in value:
                if v not in options:
                    errors.append("multiselect_value_not_in_options")
                    break

    return errors


def validate_form_response(
    fields: Iterable[Any],
    responses: Mapping[str, Any],
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Validate `responses` against the iterable of FormField rows.

    `fields` is anything iterable that yields objects with attributes:
    field_code, field_type, options (JSON or None), validation (JSON or None),
    is_active. Inactive fields are skipped.

    Returns (errors, normalised). `errors` is empty when valid.
    """
    errors: dict[str, list[str]] = {}
    normalised: dict[str, Any] = {}

    for field in fields:
        if not getattr(field, "is_active", True):
            continue

        code = field.field_code
        ftype = field.field_type
        raw = responses.get(code)
        value = _coerce_value(ftype, raw)
        normalised[code] = value

        rules = {}
        if field.validation:
            try:
                rules = json.loads(field.validation)
            except json.JSONDecodeError:
                rules = {}

        options: list[str] | None = None
        if field.options:
            try:
                options_parsed = json.loads(field.options)
                if isinstance(options_parsed, list) and len(options_parsed) > 0:
                    options = options_parsed
            except json.JSONDecodeError:
                options = None

        field_errors = _check_rules(value, rules, options, ftype)
        if field_errors:
            errors[code] = field_errors

    return errors, normalised
