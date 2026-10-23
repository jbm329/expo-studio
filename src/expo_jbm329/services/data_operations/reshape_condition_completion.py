"""Quote-aware column completion ranges for manual Reshape conditions."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ColumnCompletion:
    """Python character range to replace and decoded column-name prefix."""

    start: int
    end: int
    prefix: str


def column_completion(text: str, position: int) -> ColumnCompletion | None:
    """Find a bracketed column at the caret, ignoring single-quoted values.

    Args:
        text: Complete condition text.
        position: Caret offset in Python characters.

    Returns:
        Replacement range and prefix, or None outside a column name.
    """
    index = 0
    opening: int | None = None
    quoted = False
    prefix: list[str] = []
    while index < position:
        character = text[index]
        if quoted:
            if character == "'":
                if index + 1 < position and text[index + 1] == "'":
                    index += 2
                    continue
                quoted = False
        elif opening is not None:
            if character == "]":
                if index + 1 < position and text[index + 1] == "]":
                    prefix.append("]")
                    index += 2
                    continue
                opening = None
                prefix = []
            else:
                prefix.append(character)
        elif character == "'":
            quoted = True
        elif character == "[":
            opening = index
        index += 1
    if opening is None:
        return None
    end = position
    while index < len(text):
        if text[index] == "]":
            if index + 1 < len(text) and text[index + 1] == "]":
                index += 2
                continue
            end = index + 1
            break
        index += 1
    return ColumnCompletion(opening, end, "".join(prefix))
