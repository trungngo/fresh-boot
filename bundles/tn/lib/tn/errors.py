"""The exceptions that carry tn's exit codes (spec §2.6, §5.4)."""

from __future__ import annotations


class TnError(Exception):
    """Base of the errors core prints as ``tn: <message>`` and turns into an exit status."""

    code = 1

    def __init__(self, message: str, *, fix: str | None = None, hint: str | None = None,
                 choices: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.hint = hint
        self.choices = list(choices) if choices is not None else None

    def to_json(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "fix": self.fix,
                          "hint": self.hint, "choices": self.choices}}


class Fail(TnError):
    """Exit 1: the command ran and something went wrong (or was cancelled)."""

    code = 1

    def __init__(self, message: str, hint: str | None = None, *, fix: str | None = None) -> None:
        super().__init__(message, fix=fix, hint=hint)


class UsageError(TnError):
    """Exit 2: bad arguments, a missing target that could not be asked for, and so on."""

    code = 2

    def __init__(self, message: str, choices: list[str] | None = None,
                 hint: str | None = None) -> None:
        super().__init__(message, hint=hint, choices=choices)


class Missing(TnError):
    """Exit 3: a missing prerequisite. ``fix`` is required: it is printed as ``  run: <fix>``."""

    code = 3

    def __init__(self, what: str, fix: str, hint: str | None = None) -> None:
        if not fix:
            raise ValueError("Missing needs a fix")
        super().__init__(what, fix=fix, hint=hint)


class Problem(Exception):
    """Raised by a doctor check: one row with ``level`` "fail" or "warn"."""

    def __init__(self, message: str, fix: str | None = None, level: str = "fail") -> None:
        if level not in ("fail", "warn"):
            raise ValueError("Problem level must be 'fail' or 'warn'")
        super().__init__(message)
        self.message = message
        self.fix = fix
        self.level = level


class Cancelled(Fail):
    """The user cancelled a prompt: ``tn: cancelled``, exit 1."""

    def __init__(self) -> None:
        super().__init__("cancelled")
