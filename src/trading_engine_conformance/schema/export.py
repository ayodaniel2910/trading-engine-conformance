"""JSON Schema export for the neutral schema's top-level and shared models."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from trading_engine_conformance.canonical import canonical_json_dumps
from trading_engine_conformance.schema.assumptions import ExecutionAssumptions
from trading_engine_conformance.schema.dataset import DatasetIdentity
from trading_engine_conformance.schema.envelope import RunArtifact
from trading_engine_conformance.schema.fills import Fill
from trading_engine_conformance.schema.holdout import HoldoutState
from trading_engine_conformance.schema.instrument import InstrumentIdentity
from trading_engine_conformance.schema.ledger import LedgerSnapshot
from trading_engine_conformance.schema.market_events import (
    Bar,
    BookDelta,
    BookSnapshot,
    Quote,
    SessionStatusEvent,
    SettlementEvent,
    Trade,
)
from trading_engine_conformance.schema.orders import OrderIntent, OrderStateTransition
from trading_engine_conformance.schema.run import EnvironmentLock, RunHeader, SourceRevision
from trading_engine_conformance.schema.signals import Signal

_EXPORTED_MODELS: dict[str, type[BaseModel]] = {
    "RunArtifact": RunArtifact,
    "RunHeader": RunHeader,
    "SourceRevision": SourceRevision,
    "EnvironmentLock": EnvironmentLock,
    "DatasetIdentity": DatasetIdentity,
    "InstrumentIdentity": InstrumentIdentity,
    "HoldoutState": HoldoutState,
    "ExecutionAssumptions": ExecutionAssumptions,
    "Signal": Signal,
    "OrderIntent": OrderIntent,
    "OrderStateTransition": OrderStateTransition,
    "Fill": Fill,
    "LedgerSnapshot": LedgerSnapshot,
    "Quote": Quote,
    "Trade": Trade,
    "BookDelta": BookDelta,
    "BookSnapshot": BookSnapshot,
    "Bar": Bar,
    "SessionStatusEvent": SessionStatusEvent,
    "SettlementEvent": SettlementEvent,
}


def export_json_schemas(output_dir: Path | None = None) -> dict[str, dict[str, object]]:
    """Return ``{model_name: json_schema_dict}`` for every exported model.

    If ``output_dir`` is given, also writes one ``<ModelName>.json`` file
    per model into that directory (created if necessary).
    """
    schemas = {name: model.model_json_schema() for name, model in _EXPORTED_MODELS.items()}
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, schema in schemas.items():
            (output_dir / f"{name}.json").write_text(canonical_json_dumps(schema), encoding="utf-8")
    return schemas
