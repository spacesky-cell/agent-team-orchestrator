"""Installed-package and built-in resource contract tests."""

from importlib import import_module, resources, util


def test_public_package_is_ato_core() -> None:
    spec = util.find_spec("ato_core")

    assert spec is not None
    package = import_module("ato_core")
    assert package.__version__


def test_built_in_roles_are_package_resources() -> None:
    spec = util.find_spec("ato_core.resources.roles")

    assert spec is not None
    role_root = resources.files("ato_core.resources.roles")
    assert role_root.joinpath("architect.yaml").is_file()
    assert role_root.joinpath("schema", "role.schema.json").is_file()

    role_module = import_module("ato_core.models.role")
    assert "architect" in role_module.RoleLoader().list_roles()
