"""Position adapters for diagnostics from the authoritative formula validator."""

from expo_jbm329.services.data_operations.derived_column.derived_column_parser import DerivedColumnFormulaError


def formula_error_span(formula: str, error: DerivedColumnFormulaError) -> tuple[int, int] | None:
    """Return a bounded formula span, excluding errors about the output name.

    Args:
        formula: Untrimmed editor text used during validation.
        error: Structured validation failure from the formula service.

    Returns:
        Python character offsets, or None for a failure without a formula span.
    """
    start = error.context.get("position")
    if not isinstance(start, int):
        return None
    end = error.context.get("end", start)
    if not isinstance(end, int):
        end = start
    start = max(0, min(start, len(formula)))
    return start, max(start, min(end, len(formula)))
