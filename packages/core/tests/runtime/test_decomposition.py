"""Task decomposition validation tests."""

import pytest


def subtask(
    subtask_id: str,
    *,
    role: str = "architect",
    dependencies: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": subtask_id,
        "name": subtask_id,
        "role": role,
        "dependencies": dependencies or [],
        "expected_output": f"output for {subtask_id}",
        "status": "pending",
    }


@pytest.mark.parametrize(
    ("subtasks", "offender"),
    [
        ([], "at least one subtask"),
        ([subtask("a"), subtask("a")], "duplicate subtask IDs: a"),
        ([subtask("a", role="missing")], "unknown roles: missing"),
        ([subtask("a", dependencies=["missing"])], "unknown dependencies: missing"),
        ([subtask("a", dependencies=["a"])], "self dependencies: a"),
        (
            [subtask("a", dependencies=["b"]), subtask("b", dependencies=["a"])],
            "dependency cycle: a, b",
        ),
    ],
)
def test_invalid_decompositions_are_rejected(
    subtasks: list[dict[str, object]], offender: str
) -> None:
    from ato_core.runtime.decomposition import InvalidDecompositionError, validate_decomposition

    with pytest.raises(InvalidDecompositionError, match=offender) as exc_info:
        validate_decomposition(subtasks, available_roles={"architect"})

    assert exc_info.value.code == "INVALID_DECOMPOSITION"


def test_valid_fan_in_preserves_input_order() -> None:
    from ato_core.runtime.decomposition import validate_decomposition

    subtasks = [
        subtask("design"),
        subtask("backend", dependencies=["design"]),
        subtask("frontend", dependencies=["design"]),
        subtask("test", dependencies=["backend", "frontend"]),
    ]

    validated = validate_decomposition(subtasks, available_roles={"architect"})

    assert [item["id"] for item in validated] == ["design", "backend", "frontend", "test"]
