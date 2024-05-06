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
        # default
        return cls.ALL
