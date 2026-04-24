"""Role definition models and loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml
from jsonschema import ValidationError, validate
from pydantic import BaseModel, Field


class Deliverable(BaseModel):
    """Expected output from a role."""

    format: str = Field(..., description="Output format (e.g., markdown, openapi, code)")
    description: str = Field(..., description="Description of the expected deliverable")


class ModelPreferences(BaseModel):
    """Optional model configuration overrides for a role."""

    temperature: Optional[float] = Field(None, ge=0, le=2)
    max_tokens: Optional[int] = Field(None, ge=1)
    preferred_provider: Optional[str] = Field(None, pattern="^(anthropic|openai|ollama)$")


class Role(BaseModel):
    """Agent role definition."""

    id: str = Field(..., description="Unique role identifier")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="Role description")
    expertise: list[str] = Field(..., min_length=1, description="Skill areas")
    tools: list[str] = Field(..., min_length=1, description="Available tools")
    system_prompt: str = Field(..., description="System prompt template")
    deliverables: list[Deliverable] = Field(..., min_length=1, description="Expected outputs")
    model_preferences: Optional[ModelPreferences] = Field(
        None, description="Optional model config overrides"
    )

    def render_prompt(self, context: str = "") -> str:
        """Render the system prompt with context injected."""
        return self.system_prompt.replace("{{context}}", context)


# Path to the roles directory
ROLES_DIR = Path(__file__).parent.parent.parent.parent.parent / "roles"
SCHEMA_PATH = ROLES_DIR / "schema" / "role.schema.json"


class RoleLoader:
    """Load and validate role definitions from YAML files."""

    def __init__(self, roles_dir: Optional[Path] = None):
        self.roles_dir = roles_dir or ROLES_DIR
        self._schema: Optional[dict] = None

    @property
    def schema(self) -> dict:
        """Load and cache the JSON Schema for validation."""
        if self._schema is None:
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                self._schema = json.load(f)
        return self._schema

    def load(self, role_id: str) -> Role:
        """Load a role by its ID (looks for <roles_dir>/<role_id>.yaml)."""
        yaml_path = self.roles_dir / f"{role_id}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(f"Role definition not found: {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Validate against JSON Schema
        try:
            validate(instance=data, schema=self.schema)
        except ValidationError as e:
            raise ValueError(f"Role '{role_id}' validation failed: {e.message}") from e

        return Role(**data)

    def list_roles(self) -> list[str]:
        """List all available role IDs."""
        if not self.roles_dir.exists():
            return []
        return [p.stem for p in sorted(self.roles_dir.glob("*.yaml"))]

    def load_all(self) -> dict[str, Role]:
        """Load all available roles."""
        return {role_id: self.load(role_id) for role_id in self.list_roles()}
