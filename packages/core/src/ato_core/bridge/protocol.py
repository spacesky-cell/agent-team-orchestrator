"""Bridge response helpers and stable errors."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BridgeResponse(BaseModel):
    """Stable one-shot response envelope."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: dict[str, Any] | None = None
    code: str | None = None
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class BridgeEvent(BaseModel):
    """Stable streaming event envelope."""

    model_config = ConfigDict(extra="forbid")

    type: str
    task_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class BridgeCommandError(RuntimeError):
    """A safe command error that can cross the process boundary."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"{code}: {message}")


def success(data: dict[str, Any]) -> dict[str, Any]:
    return BridgeResponse(ok=True, data=data).model_dump(exclude_none=True)


def failure(error: BridgeCommandError) -> dict[str, Any]:
    return BridgeResponse(
        ok=False,
        code=error.code,
        message=error.message,
        details=error.details,
    ).model_dump(exclude_none=True)
