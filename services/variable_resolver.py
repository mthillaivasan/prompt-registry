"""Runtime variable resolver for prompt placeholders.

Substitutes {variable_name} tokens in prompt text with runtime-resolved
values. Unknown placeholders pass through literally so they remain
visible in output rather than being silently dropped.

Slot A1 supports one variable: {generation_date}. Further variables
(version_number, author, etc.) are added in subsequent slots.
"""

import re
from datetime import datetime

_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class VariableResolver:
    def __init__(self) -> None:
        self._resolvers = {
            "generation_date": lambda prompt, user: datetime.utcnow().strftime("%Y-%m-%d"),
        }

    def resolve(self, text: str, prompt=None, user=None) -> str:
        def _sub(match: re.Match) -> str:
            name = match.group(1)
            resolver = self._resolvers.get(name)
            if resolver is None:
                return match.group(0)
            return resolver(prompt, user)

        return _PLACEHOLDER_RE.sub(_sub, text)
