from enum import Enum


class ExecutionMode(Enum):
    ORIGINAL_ORDER = 0
    ITERATIONS = 1
    RESULT = 2

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        raise ValueError(f"{value} is not a valid {cls.__name__}")

    @property
    def label(self) -> str:
        """Return human-readable label for the execution mode."""
        labels = {
            ExecutionMode.ORIGINAL_ORDER: "Original Order",
            ExecutionMode.ITERATIONS: "Iterations",
            ExecutionMode.RESULT: "Result",
        }
        return labels.get(self, self.name)
