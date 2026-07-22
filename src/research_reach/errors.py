"""Public errors shared by the three CLI entry points."""

from __future__ import annotations


class ResearchReachError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: str = "failed",
        exit_code: int = 4,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.exit_code = exit_code


def invalid(message: str) -> ResearchReachError:
    return ResearchReachError("INVALID_INPUT", message, exit_code=2)


def blocked(message: str) -> ResearchReachError:
    return ResearchReachError("BLOCKED", message, status="blocked", exit_code=3)
