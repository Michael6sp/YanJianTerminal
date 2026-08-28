from dataclasses import dataclass


@dataclass(frozen=True)
class AlarmTransition:
    key: str
    alarmed: bool
    label: str


class AlarmManager:
    """Deduplicates alarms and emits only ALARM/RECOVERED transitions."""

    def __init__(self) -> None:
        self._states: dict[str, bool] = {}

    def evaluate(self, key: str, alarmed: bool, label: str) -> AlarmTransition | None:
        previous = self._states.get(key)
        self._states[key] = alarmed
        if previous is None:
            return AlarmTransition(key, alarmed, label) if alarmed else None
        if previous == alarmed:
            return None
        return AlarmTransition(key, alarmed, label)

    @property
    def active_count(self) -> int:
        return sum(self._states.values())
