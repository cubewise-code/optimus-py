# src/optimuspy/order_frame.py
"""The order frame — one authoritative frame of reference for a cube's dimension order.

A cube has one authoritative dimension order: `tm1.cubes.get_storage_dimension_order()`.
The frame owns that order and answers one question: is this candidate order
admissible, and if not, why.

If the dimension in the **last position** of the storage order contains string
elements, that position is a **locked slot**: the dimension never moves, whatever
the order source. This is a *server* constraint — TM1 rejects the write regardless
— so every order source consults the frame, and a candidate that would move the
locked dimension is skipped with a logged reason. Nothing is ever relocated.

Everything else the frame knows — position rules, excluded dimensions, ignored
orders — is a *user preference*, supplied by the greedy folds only. A TM1 developer
who names an explicit order in `predefined_orders` or set mode gets it, subject to
the lock alone.

Pure: no `TM1Service`, no I/O, and no logging of its own — `admits` returns the
reason and the caller decides how to report it. Offline-testable in the same
category as `tau.py`.

See CONTEXT.md ("Order admissibility") and docs/concepts/string-element-constraint.md.
"""
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

# Greppable codes for the reasons a candidate order is refused. The human-readable
# message travels alongside in `Admissibility.reason`.
REASON_NOT_A_PERMUTATION = "not_a_permutation"
REASON_LOCKED_SLOT = "locked_slot"
REASON_IGNORED_ORDER = "ignored_order"
REASON_POSITION_RULE = "position_rule"


class Admissibility(NamedTuple):
    """The frame's verdict on one candidate order.

    `code` is stable and greppable (for tests and log filtering); `reason` is the
    sentence a caller logs. Both are None when the order is admissible.
    """
    admissible: bool
    code: Optional[str] = None
    reason: Optional[str] = None


ADMISSIBLE = Admissibility(True)


class OrderFrame:
    """A cube's storage order plus the rules that decide which orders are allowed.

    Non-greedy callers construct it with the storage order and the lock alone, so
    only the server constraint applies. The greedy folds additionally supply the
    user preferences.
    """

    def __init__(self, storage_order: Sequence[str], last_slot_locked: bool, *,
                 dimensions_to_exclude: Sequence[str] = None,
                 orders_to_ignore: Sequence[Sequence[str]] = None,
                 position_rules: Sequence[Dict] = None):
        self.storage_order = list(storage_order)
        self.last_slot_locked = bool(last_slot_locked)
        self.dimensions_to_exclude = list(dimensions_to_exclude or [])
        self.orders_to_ignore = [list(order) for order in (orders_to_ignore or [])]
        self.position_rules = list(position_rules or [])
        self._dimensions = frozenset(self.storage_order)
        self._pinned = self._resolve_pins()

    def _resolve_pins(self) -> Dict[int, str]:
        """{slot: dimension} for the rules that name a real dimension and a real slot.

        A rule that names neither is skipped here and reported by
        `validate_position_rules`. It must not silently constrain the search:
        pinning an unreadable rule would reserve a slot nobody asked for.

        Conflicts — two rules on one slot, or one dimension named twice — keep
        the first rule so the frame stays deterministic while validation reports
        the conflict.
        """
        pins = {}
        for rule in self.position_rules:
            if not isinstance(rule, dict):
                continue
            dimension = rule.get('dimension')
            if dimension not in self._dimensions or dimension in pins.values():
                continue
            index = self.required_index(rule.get('position'), len(self.storage_order))
            if index is None or index in pins:
                continue
            pins[index] = dimension
        return pins

    @property
    def pinned_positions(self) -> Dict[int, str]:
        """The slots a position rule seats a dimension in, as {slot: dimension}."""
        return dict(self._pinned)

    def pre_applied_order(self) -> List[str]:
        """The storage order with every pinned dimension seated at its slot.

        This — not the storage order — is where a greedy search starts when
        position rules are set: the documented behaviour is to seat the pinned
        dimensions and search the slots that are left (see
        docs/advanced/dimension-position-rules.md). The remaining dimensions keep
        their relative storage-order sequence in the slots that remain.
        """
        if not self._pinned:
            return list(self.storage_order)
        seated = [None] * len(self.storage_order)
        for index, dimension in self._pinned.items():
            seated[index] = dimension
        rest = (d for d in self.storage_order if d not in self._pinned.values())
        return [d if d is not None else next(rest) for d in seated]

    @property
    def locked_dimension(self) -> Optional[str]:
        """The dimension pinned to the last slot, or None when that slot is free."""
        if not self.last_slot_locked or not self.storage_order:
            return None
        return self.storage_order[-1]

    @property
    def locked_position(self) -> Optional[int]:
        """The index of the locked slot, or None when there is no lock."""
        if not self.last_slot_locked or not self.storage_order:
            return None
        return len(self.storage_order) - 1

    def movable_dimensions(self) -> List[str]:
        """Dimensions the greedy may relocate: everything that is not held in place.

        Three things hold a dimension: the lock (it never moves), an exclusion
        (frozen at its original index by user preference), and a position rule
        (seated at the slot the user named). They are different reasons for the
        same fact, and the search only needs the fact.
        """
        locked = self.locked_dimension
        pinned = set(self._pinned.values())
        return [d for d in self.storage_order
                if d not in self.dimensions_to_exclude and d != locked and d not in pinned]

    def reserved_positions(self) -> Set[int]:
        """Slots that are never a sweep target: excluded, locked and pinned.

        Note these index the **pre-applied** order, which is what the greedy
        searches. They coincide with the storage order's indices for everything
        except a pinned dimension, whose slot is the one its rule names.
        """
        reserved = {i for i, d in enumerate(self.pre_applied_order())
                    if d in self.dimensions_to_exclude}
        locked_position = self.locked_position
        if locked_position is not None:
            reserved.add(locked_position)
        reserved.update(self._pinned)
        return reserved

    def admits(self, candidate_order: Sequence[str]) -> Admissibility:
        """Is this candidate order allowed? Returns the reason when it is not.

        The server constraint (the locked slot) is checked before any user
        preference, so a refusal always names the strongest reason.
        """
        candidate = list(candidate_order)

        if len(candidate) != len(self.storage_order) or frozenset(candidate) != self._dimensions:
            return Admissibility(
                False, REASON_NOT_A_PERMUTATION,
                f"order is not a permutation of the cube's dimensions "
                f"{self.storage_order}: {candidate}")

        locked = self.locked_dimension
        if locked is not None and candidate[-1] != locked:
            return Admissibility(
                False, REASON_LOCKED_SLOT,
                f"'{locked}' has string elements and is locked to the last position; "
                f"this order moves it to position {candidate.index(locked)}")

        if candidate in self.orders_to_ignore:
            return Admissibility(
                False, REASON_IGNORED_ORDER,
                f"order is listed in orders_to_ignore: {candidate}")

        unsatisfied = self._unsatisfied_position_rule(candidate)
        if unsatisfied is not None:
            dimension, actual_index, required_index = unsatisfied
            return Admissibility(
                False, REASON_POSITION_RULE,
                f"dimension_position_rules: '{dimension}' must be at position "
                f"{required_index}, this order puts it at {actual_index}")

        return ADMISSIBLE

    def _unsatisfied_position_rule(
            self, candidate: List[str]) -> Optional[Tuple[str, int, int]]:
        """The first pin this order fails, as (dimension, actual, required).

        A rule is *satisfied* when the dimension is at the position it names —
        that is the layout the user asked to lock. It reads the resolved pins
        rather than the raw rules, so there is one place a rule is turned into a
        slot; a rule that resolves to no slot is reported by
        `validate_position_rules` and constrains nothing here.

        With pre-application in place the greedy should never generate a
        violating order at all — the pinned slots are reserved. This stays as the
        check that says so.
        """
        for required_index, dimension in self._pinned.items():
            actual_index = candidate.index(dimension)
            if actual_index != required_index:
                return dimension, actual_index, required_index
        return None

    @staticmethod
    def required_index(position, dimension_count: int) -> Optional[int]:
        """The 0-based slot a rule's `position` names, or None if it names no slot.

        'first' and 'last' resolve to the end slots; an int is taken as written,
        0-based. Everything else resolves to None: a word that is not a keyword, a
        float (truncating 2.7 to 2 would silently reinterpret a malformed config),
        a bool, and — the reason `dimension_count` is a parameter — any index the
        cube does not have, whether too large or negative.

        None means "this rule names no slot", which `_unsatisfied_position_rule`
        passes over. Turning these into the errors the documentation promises is
        startup validation's job, where the message can name the config field.
        """
        if position == 'first':
            return 0
        if position == 'last':
            return dimension_count - 1
        # bool is a subclass of int, so True would otherwise resolve to slot 1.
        if isinstance(position, bool) or not isinstance(position, int):
            return None
        return position if 0 <= position < dimension_count else None

    @staticmethod
    def _intended_index(position) -> Optional[int]:
        """The slot a value plainly means, even though its type is not an integer.

        `"3"` and `3.0` name slot 3 unambiguously and are refused only because
        the documented type is an integer. Reporting those as an unreadable
        position, at a value the user can see is a number, reads as an accusation
        of a typo. `"middle"` and `2.7` genuinely name no slot and get None.
        """
        if isinstance(position, bool):
            return None
        if isinstance(position, int):
            # In range it would have resolved already, so this is an integer the
            # cube has no slot for: the range is the useful thing to say.
            return position
        if isinstance(position, float):
            return int(position) if position.is_integer() else None
        if isinstance(position, str):
            text = position.strip()
            try:
                return int(text)
            except ValueError:
                return None
        return None

    def validate_position_rules(self) -> List[Tuple[int, str]]:
        """Every problem with the configured rules, as (rule index, message).

        Pure: it reports, the caller raises. All of them are reported, not just
        the first, so a rewritten config is checked in one pass.

        This is where each case `required_index` defers becomes the error the
        documentation promises. Silently ignoring them would mean a typo'd rule
        constrains nothing while the run reports success over a search nobody
        asked for.
        """
        count = len(self.storage_order)
        problems = []
        seen_dimension, seen_position = {}, {}

        for index, rule in enumerate(self.position_rules):
            if not isinstance(rule, dict) or 'dimension' not in rule or 'position' not in rule:
                problems.append((index, "must have a 'dimension' and a 'position'"))
                continue
            dimension, position = rule['dimension'], rule['position']

            if dimension not in self._dimensions:
                problems.append((index, f"'{dimension}' is not a dimension of this cube"))
                continue
            if dimension in seen_dimension:
                problems.append((index, f"'{dimension}' already has a rule at "
                                        f"dimension_position_rules[{seen_dimension[dimension]}]"))
                continue
            seen_dimension[dimension] = index

            if dimension in self.dimensions_to_exclude:
                problems.append((index, f"'{dimension}' is also in dimensions_to_exclude — "
                                        f"one says leave it where it is, the other says move "
                                        f"it to a specific slot"))
                continue

            slot = self.required_index(position, count)
            if slot is None:
                intended = self._intended_index(position)
                if intended is None:
                    problems.append((index, f"position {position!r} names no slot — use a "
                                            f"0-based integer, or 'first' or 'last'"))
                elif not 0 <= intended < count:
                    problems.append((index, f"position {intended} is out of range for a "
                                            f"{count}-dimension cube (0-{count - 1})"))
                else:
                    problems.append((index, f"position must be an integer — "
                                            f"write {intended}, not {position!r}"))
                continue

            if slot in seen_position:
                problems.append((index, f"position {slot} is already taken by "
                                        f"dimension_position_rules[{seen_position[slot]}]"))
                continue
            seen_position[slot] = index

            locked = self.locked_dimension
            if locked is not None:
                if dimension == locked and slot != self.locked_position:
                    problems.append((index, f"'{dimension}' has string elements and is locked "
                                            f"to position {self.locked_position}; this rule "
                                            f"places it at {slot}"))
                elif dimension != locked and slot == self.locked_position:
                    problems.append((index, f"position {slot} holds '{locked}', which has string "
                                            f"elements and never moves; it cannot be given to "
                                            f"'{dimension}'"))

        return problems
