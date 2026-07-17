"""AppSpec transition effect validation."""
from __future__ import annotations

from typing import Any, Dict

from app.domain.appspec.validation.collector import _Collector, _require_reference
from app.domain.appspec.validation.models import IssuePath
from app.domain.schemas.app_spec import EntityField

def _validate_effect(
    collector: _Collector,
    effect: Any,
    path: IssuePath,
    entities: Dict[str, Any],
    fields: Dict[str, EntityField],
) -> None:
    entity = _require_reference(
        collector, effect.entity_id, entities, path + ("entity_id",), "entity"
    )
    field = _require_reference(
        collector, effect.field_id, fields, path + ("field_id",), "entity field"
    )
    if entity is not None and field is not None and field not in entity.fields:
        collector.add(
            "effect_field_entity_mismatch",
            f"Field {field.id!r} does not belong to entity {entity.id!r}.",
            path + ("field_id",),
            (entity.id, field.id),
        )
    if effect.operation == "clear":
        if effect.value is not None:
            collector.add(
                "clear_effect_has_value",
                "A clear effect must not declare value.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )
        return
    if effect.value is None:
        collector.add(
            "effect_value_required",
            f"Effect operation {effect.operation!r} requires value.",
            path + ("value",),
            (effect.entity_id, effect.field_id),
        )
        return
    if field is None:
        return
    value = effect.value
    if effect.operation in {"increment", "decrement"}:
        if field.type not in {"integer", "number"} or isinstance(value, bool) or not isinstance(value, (int, float)):
            collector.add(
                "numeric_effect_type_mismatch",
                f"{effect.operation.title()} requires a numeric field and numeric value.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )
    elif effect.operation in {"append", "remove"}:
        if field.type != "list":
            collector.add(
                "collection_effect_type_mismatch",
                f"{effect.operation.title()} requires a list field.",
                path + ("field_id",),
                (effect.entity_id, effect.field_id),
            )
    elif effect.operation == "set":
        valid = True
        if field.type in {"string", "date", "datetime", "reference", "enum"}:
            valid = isinstance(value, str)
        elif field.type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif field.type == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif field.type == "boolean":
            valid = isinstance(value, bool)
        if not valid:
            collector.add(
                "set_effect_type_mismatch",
                f"Set value is incompatible with field {field.id!r} of type {field.type!r}.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )
        if field.type == "enum" and isinstance(value, str) and value not in field.enum_values:
            collector.add(
                "enum_effect_value_unknown",
                f"Value {value!r} is not allowed by enum field {field.id!r}.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )
