"""Helpers for building SCB PxWeb queries."""
from __future__ import annotations

from dataclasses import dataclass, field


class ScbQueryError(ValueError):
    """Raised when an SCB query cannot be built."""


@dataclass(frozen=True)
class ScbSelection:
    """A single SCB variable selection.

    The selected values are encoded as a comma-separated list in the final
    PxWeb query parameters, matching the SCB API contract.
    """

    variable: str
    values: tuple[str, ...] = field(default_factory=tuple)
    codelist: str | None = None

    def __post_init__(self) -> None:
        variable_name = str(self.variable).strip()
        if not variable_name:
            raise ScbQueryError("SCB variable name must not be empty")

        cleaned_values = tuple(
            str(value).strip() for value in self.values if str(value).strip()
        )
        if not cleaned_values:
            raise ScbQueryError(
                f"SCB selection for '{variable_name}' requires at least one selected values entry"
            )

        object.__setattr__(self, "variable", variable_name)
        object.__setattr__(self, "values", cleaned_values)


class ScbQueryBuilder:
    """Build valid SCB PxWeb query parameters for table downloads."""

    def build(
        self,
        *,
        table_id: str,
        selections: list[ScbSelection] | tuple[ScbSelection, ...],
        lang: str = "sv",
        output_format: str = "json-stat2",
    ) -> dict[str, str]:
        """Build SCB query parameters from a table id and selected values.

        Args:
            table_id: SCB table id such as "TAB6471".
            selections: Variable choices to include in the query.
            lang: Language code such as "sv" or "en".
            output_format: SCB response format. Defaults to "json-stat2".

        Returns:
            Dictionary of query parameters suitable for httpx or requests.

        Raises:
            ScbQueryError: If the parameters are invalid.
        """
        cleaned_table_id = str(table_id).strip()
        if not cleaned_table_id:
            raise ScbQueryError("SCB table id must not be empty")

        if not selections:
            raise ScbQueryError("At least one SCB selection is required")

        params: dict[str, str] = {
            "lang": str(lang).strip() or "sv",
            "outputFormat": output_format,
        }

        seen: set[str] = set()
        for selection in selections:
            name = str(selection.variable).strip()
            if not name:
                raise ScbQueryError("SCB selection variable name must not be empty")
            if name in seen:
                raise ScbQueryError(f"Duplicate SCB selection for '{name}'")
            seen.add(name)

            params[f"valueCodes[{name}]"] = ",".join(selection.values)
            if selection.codelist:
                params[f"codelist[{name}]"] = str(selection.codelist).strip()

        return params

    @staticmethod
    def table_url(table_id: str) -> str:
        """Return the SCB table data endpoint for a table id."""
        cleaned_table_id = str(table_id).strip()
        if not cleaned_table_id:
            raise ScbQueryError("SCB table id must not be empty")
        return f"https://statistikdatabasen.scb.se/api/v2/tables/{cleaned_table_id}/data"
