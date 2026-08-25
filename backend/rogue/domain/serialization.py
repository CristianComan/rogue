"""Generic JSON/YAML round-trip helpers for domain models.

Pydantic v2 already provides JSON round-tripping (``model_dump_json`` /
``model_validate_json``); this module adds YAML on top, since ``pyyaml`` is
a project dependency but has no first-class pydantic integration. Values
are dumped through ``model_dump(mode="json")`` first so UUIDs, datetimes,
timedeltas and enums come out as their JSON-safe (and therefore
YAML-safe) primitive representations.
"""

from __future__ import annotations

import yaml
from pydantic import BaseModel


def to_json(model: BaseModel) -> str:
    """Serialize a domain model to a JSON string."""
    return model.model_dump_json(indent=2)


def from_json[ModelT: BaseModel](model_type: type[ModelT], data: str) -> ModelT:
    """Deserialize a domain model from a JSON string."""
    return model_type.model_validate_json(data)


def to_yaml(model: BaseModel) -> str:
    """Serialize a domain model to a YAML string."""
    return yaml.safe_dump(model.model_dump(mode="json"), sort_keys=False)


def from_yaml[ModelT: BaseModel](model_type: type[ModelT], data: str) -> ModelT:
    """Deserialize a domain model from a YAML string."""
    return model_type.model_validate(yaml.safe_load(data))
