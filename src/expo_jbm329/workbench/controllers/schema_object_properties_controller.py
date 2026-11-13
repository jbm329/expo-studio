"""Own asynchronous schema-object Properties dialog requests."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from threading import Event
from typing import TYPE_CHECKING

from PyQt6 import sip
from PyQt6.QtCore import QT_TRANSLATE_NOOP

from expo_jbm329.db.base import get_object_properties
from expo_jbm329.gui.dialogs.schema_object_properties_dialog import SchemaObjectPropertiesDialog
from expo_jbm329.utils.i18n_utils import translate, translate_fmt

# Catalog diagnostics originate in the Qt-free metadata loader.
CATALOG_ERROR_MESSAGES = (
    QT_TRANSLATE_NOOP("DbErrors", "Object properties retrieval did not complete."),
    QT_TRANSLATE_NOOP("DbErrors", "Object properties query returned no result set."),
    QT_TRANSLATE_NOOP("DbErrors", "The object does not exist or is not visible in the selected database."),
    QT_TRANSLATE_NOOP("DbErrors", "Object columns are no longer available or are not visible."),
    QT_TRANSLATE_NOOP("DbErrors", "The object changed while its properties were being loaded."),
    QT_TRANSLATE_NOOP("DbErrors", "The object changed while its properties were being loaded. Retry the request."),
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

    from expo_jbm329.db.core.object_properties import ObjectProperties, SchemaObjectIdentity
    from expo_jbm329.workbench.controllers.async_operation_controller import AsyncOperationController


@dataclass
class _Session:
    connection: str
    dialog: SchemaObjectPropertiesDialog
    invalidated: Event = field(default_factory=Event)
    generation: int = 0


@dataclass(frozen=True)
class _Failure:
    message: str


class SchemaObjectPropertiesController:
    """Orchestrate requests without retaining schema tree items."""

    TR_LOAD = QT_TRANSLATE_NOOP("SchemaObjectPropertiesController", "Load object properties")
    TR_FAILED = QT_TRANSLATE_NOOP("SchemaObjectPropertiesController", "Could not load properties.\n\n{error}")
    TR_CANCELLED = QT_TRANSLATE_NOOP("SchemaObjectPropertiesController", "Properties loading did not complete.")

    def __init__(
        self,
        *,
        parent: QWidget,
        async_ops: AsyncOperationController,
        load: Callable[..., ObjectProperties] = get_object_properties,
    ) -> None:
        """Inject the existing async runner and database facade."""
        self._parent = parent
        self._async_ops = async_ops
        self._load = load
        self._sessions: list[_Session] = []
        self._logger = logging.getLogger("applogger.ui")

    def open(self, connection: str, identity: SchemaObjectIdentity) -> SchemaObjectPropertiesDialog:
        """Open a modeless dialog bound to a captured connection and identity."""
        dialog = SchemaObjectPropertiesDialog(self._parent, identity)
        session = _Session(connection, dialog)
        self._sessions.append(session)

        def close() -> None:
            session.invalidated.set()
            if session in self._sessions:
                self._sessions.remove(session)

        dialog.finished.connect(close)
        dialog.destroyed.connect(close)
        dialog.retry_requested.connect(lambda: self._start(session, identity))
        dialog.show()
        self._start(session, identity)
        return dialog

    def invalidate_connection(self, connection: str) -> None:
        """Ignore all replies for a disconnected, replaced or deleted connection."""
        for session in self._sessions:
            if session.connection == connection:
                session.invalidated.set()
                if not sip.isdeleted(session.dialog):
                    session.dialog.show_connection_changed()

    def _start(self, session: _Session, identity: SchemaObjectIdentity) -> None:
        if session.invalidated.is_set() or sip.isdeleted(session.dialog):
            return
        session.generation += 1
        generation = session.generation
        dialog = session.dialog
        dialog.set_loading()
        handled = False
        operation = translate("SchemaObjectPropertiesController", self.TR_LOAD)
        incomplete = translate("SchemaObjectPropertiesController", self.TR_CANCELLED)
        corr_id = uuid.uuid4().hex

        def stale() -> bool:
            return session.invalidated.is_set() or sip.isdeleted(dialog) or session.generation != generation

        def work(*, cancel_cb: Callable[[], bool] | None = None, **_: object) -> ObjectProperties | _Failure | None:
            if session.invalidated.is_set() or (cancel_cb is not None and cancel_cb()):
                return None
            try:
                return self._load(session.connection, identity, corr_id=corr_id)
            except RuntimeError as exc:
                self._logger.exception("Properties catalog request failed (corr=%s).", corr_id)
                return _Failure(str(exc))
            except (ValueError, TypeError, KeyError):
                self._logger.exception("Properties catalog data is invalid (corr=%s).", corr_id)
                return _Failure(incomplete)

        def result(snapshot: ObjectProperties | _Failure | None) -> None:
            nonlocal handled
            if stale():
                return
            handled = True
            if snapshot is None:
                dialog.show_problem(incomplete)
            elif isinstance(snapshot, _Failure):
                message = "\n\n".join(translate("DbErrors", part) for part in snapshot.message.split("\n\n"))
                dialog.show_problem(translate_fmt("SchemaObjectPropertiesController", self.TR_FAILED, error=message))
            else:
                dialog.show_properties(snapshot)

        def error(_traceback: str) -> None:
            nonlocal handled
            self._logger.error("Properties retrieval failed (connection=%s, corr=%s).", session.connection, corr_id)
            if stale():
                return
            handled = True
            # Worker tracebacks are internal diagnostics, not user-facing metadata.
            dialog.show_problem(translate_fmt("SchemaObjectPropertiesController", self.TR_FAILED, error=incomplete))

        def finished() -> None:
            if not stale() and not handled:
                dialog.show_problem(incomplete)

        self._async_ops.run_operation(
            runner="thread",
            work=work,
            on_result=result,
            on_error=error,
            on_finished=finished,
            busy_message=operation,
            operation_name=operation,
            scope=f"schema:properties:{uuid.uuid4().hex}",
            corr_id=corr_id,
            stale_check=stale,
            foreground=False,
            show_overlay=False,
            cancelable=False,
        )
