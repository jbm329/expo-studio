"""Qt-free literal decoding and nullable comparison primitives."""

from __future__ import annotations

import pandas as pd


class UnclosedLiteralError(ValueError):
    """A quoted string or bracketed reference has no closing delimiter."""

    def __init__(self, start: int, end: int) -> None:
        """Capture the unterminated source span."""
        self.start = start
        self.end = end
        super().__init__(f"Unclosed literal at position {start}.")


def decode_delimited_literal(text: str, start: int) -> tuple[str, int]:
    """Decode a string or column reference with doubled closing delimiters.

    Args:
        text: Complete source expression.
        start: Position of the opening apostrophe or bracket.

    Returns:
        Decoded text and the position immediately after its closing delimiter.

    Raises:
        ValueError: If start does not identify a supported opening delimiter.
        UnclosedLiteralError: If the closing delimiter is missing.
    """
    if not 0 <= start < len(text) or text[start] not in {"[", "'"}:
        message = "Expected an apostrophe or opening bracket at the literal start."
        raise ValueError(message)
    closing = "]" if text[start] == "[" else "'"
    position = start + 1
    decoded: list[str] = []
    while position < len(text):
        if text[position] != closing:
            decoded.append(text[position])
            position += 1
        elif position + 1 < len(text) and text[position + 1] == closing:
            decoded.append(closing)
            position += 2
        else:
            return "".join(decoded), position + 1
    raise UnclosedLiteralError(start, len(text))


def _comparison_mask(mask: pd.Series, missing: pd.Series, *, preserve_unknown: bool) -> pd.Series:
    if preserve_unknown:
        return mask.astype("boolean").mask(missing, pd.NA)
    return (mask.fillna(False) & ~missing).astype(bool)


def compare_values(
    left: pd.Series,
    right: object,
    operator: str,
    *,
    preserve_unknown: bool,
) -> pd.Series:
    """Compare operands without coercing source values or hiding type errors.

    Args:
        left: Source values and output index.
        right: A scalar or an identically indexed Series.
        operator: One of =, !=, >, >=, < or <=.
        preserve_unknown: Retain missing operands as nullable Boolean unknowns;
            otherwise exclude them with a nonnullable false mask.

    Returns:
        Boolean comparison mask with the source index.

    Raises:
        ValueError: If the operator or operand indexes are incompatible.
        TypeError: If pandas cannot compare the operand types.
    """
    if operator not in {"=", "!=", ">", ">=", "<", "<="}:
        message = f"Unsupported comparison operator: {operator!r}."
        raise ValueError(message)
    if isinstance(right, pd.Series):
        if not left.index.equals(right.index):
            message = "Comparison operands must have identical indexes."
            raise ValueError(message)
        missing = left.isna() | right.isna()
    else:
        if not pd.api.types.is_scalar(right):
            message = "Comparison requires a scalar or Series operand."
            raise TypeError(message)
        if pd.Series([right], dtype=object).isna().any():
            return pd.Series(
                pd.NA if preserve_unknown else False,
                index=left.index,
                name=left.name,
                dtype="boolean" if preserve_unknown else bool,
            )
        missing = left.isna()
    match operator:
        case "=":
            mask = left == right
        case "!=":
            mask = left != right
        case ">":
            mask = left > right
        case ">=":
            mask = left >= right
        case "<":
            mask = left < right
        case _:
            mask = left <= right
    return _comparison_mask(mask, missing, preserve_unknown=preserve_unknown)


def membership_mask(
    source: pd.Series,
    values: pd.Series,
    *,
    negate: bool = False,
    preserve_unknown: bool,
) -> pd.Series:
    """Test membership with an explicit missing-value policy.

    Args:
        source: Source values and output index.
        values: Candidate scalar values.
        negate: Evaluate NOT IN instead of IN.
        preserve_unknown: Preserve missing source values and unmatched rows
            with a missing candidate as unknown, following SQL semantics.

    Returns:
        Boolean membership mask without modifying either operand.
    """
    mask = source.isin(values)
    missing = source.isna()
    if preserve_unknown and values.isna().any():
        missing = missing | ~mask
    if negate:
        mask = ~mask
    return _comparison_mask(mask, missing, preserve_unknown=preserve_unknown)
