from dataclasses import dataclass, field
from typing import Any


@dataclass
class TerminalState:
    values: dict[str, Any] = field(default_factory=dict)

    def update(self, values: dict[str, Any]) -> None:
        self.values.update(values)

    def get(self, key: str, default: Any = "--") -> Any:
        value = self.values.get(key, default)
        return default if value is None else value
