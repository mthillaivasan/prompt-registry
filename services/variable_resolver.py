"""Runtime variable resolver — pure string substitution.

Substitutes {variable_name} tokens in prompt text with values supplied
by the caller as keyword arguments. The resolver has no knowledge of
domain objects or the database; callers look up and format values
before calling resolve().

A placeholder resolves when its kwarg is not None.
Note: empty string '' resolves to '' (explicit empty signal from
caller), integer 0 resolves to '0'. Only None triggers the
literal-placeholder fallback.

Supported: {generation_date}, {version_number}, {author}. Adding a new
variable: one kwarg on resolve() + one entry in the dispatch dict.
"""

import re

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class VariableResolver:
    def resolve(
        self,
        text: str,
        *,
        generation_date: str | None = None,
        version_number: int | str | None = None,
        author: str | None = None,
    ) -> str:
        values = {
            "generation_date": generation_date,
            "version_number": version_number,
            "author": author,
        }

        def _sub(match: re.Match) -> str:
            value = values.get(match.group(1))
            if value is None:
                return match.group(0)
            return str(value)

        return _PLACEHOLDER_RE.sub(_sub, text)
