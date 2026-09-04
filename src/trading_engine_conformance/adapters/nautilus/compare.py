"""Event-by-event discrepancy records; differences are never erased."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClassifiedDifference:
    field: str
    oracle_value: Any
    nautilus_value: Any
    classification: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "oracle_value": self.oracle_value,
            "nautilus_value": self.nautilus_value,
            "classification": self.classification,
        }


def classify_difference(field: str, oracle_value: Any, nautilus_value: Any) -> ClassifiedDifference:
    lowered = field.lower()
    if "instrument" in lowered or "symbol" in lowered:
        classification = "input_mapping"
    elif "timestamp" in lowered or "_ts" in lowered or "eligib" in lowered:
        classification = "timestamp_eligibility_rule"
    elif "fee" in lowered or "margin" in lowered or "cash" in lowered or "pnl" in lowered:
        classification = "accounting_convention"
    elif "unsupported" in lowered or "bar" in lowered:
        classification = "unsupported_semantics"
    elif "fill" in lowered or "price" in lowered or "quantity" in lowered:
        classification = "execution_model_choice"
    else:
        classification = "unresolved"
    return ClassifiedDifference(field, oracle_value, nautilus_value, classification)
