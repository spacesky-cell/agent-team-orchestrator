"""JSON Schema to Pydantic conversion tests."""

import pytest
from pydantic import ValidationError


def test_read_file_path_is_required() -> None:
    from ato_core.tools.file_ops import ReadFileTool
    from ato_core.tools.schema import pydantic_model_for_tool

    model = pydantic_model_for_tool(ReadFileTool.parameters, "ReadFileArgs")
    schema = model.model_json_schema()

    assert schema["required"] == ["path"]
    assert schema["properties"]["path"]["description"] == "Path to the file to read"
    with pytest.raises(ValidationError):
        model()


def test_optional_defaults_and_unknown_fields_are_validated() -> None:
    from ato_core.tools.file_ops import WriteFileTool
    from ato_core.tools.schema import pydantic_model_for_tool

    model = pydantic_model_for_tool(WriteFileTool.parameters, "WriteFileArgs")
    parsed = model(path="a.txt", content="hello")

    assert parsed.encoding == "utf-8"
    assert parsed.mode == "write"
    with pytest.raises(ValidationError):
        model(path="a.txt", content="hello", unexpected=True)
