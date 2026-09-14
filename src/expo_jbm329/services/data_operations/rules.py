"""Rule-based DataFrame transformation engine.

This module provides a lightweight rule abstraction for applying
repeatable, composable DataFrame transformations.

It is intended as a foundation for:
- UI-driven transformation pipelines
- Serializable transformation steps
- Batch or preview-based data cleaning workflows

Design principles:
- Side-effect free: rules always return new DataFrames
- Explicit, single-responsibility rules
- Easy extensibility via subclassing
- No UI dependencies
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .text import clean_text, replace_values

logger = logging.getLogger("applogger.service")


# =====================================================================
# Base rule abstraction
# =====================================================================

@dataclass(frozen=True)
class Rule:
    """Base class for DataFrame transformation rules.

    A rule represents a single, deterministic transformation
    applied to a DataFrame.

    Subclasses must implement `apply`.
    """

    column: str

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply the rule to a DataFrame.

        Args:
            df: Source DataFrame.

        Returns:
            A new DataFrame after applying the rule.

        Raises:
            NotImplementedError: If not implemented by subclass.
        """
        raise NotImplementedError("Rule.apply must be implemented by subclasses")


# =====================================================================
# Concrete rules
# =====================================================================

@dataclass(frozen=True)
class ReplaceRule(Rule):
    """Replace values in a column.

    Supports both literal and regex-based replacement.
    """

    pattern: Any
    replacement: Any
    regex: bool = False

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply value replacement to the DataFrame."""
        logger.debug(
            "Apply ReplaceRule: col='%s' pattern=%r replacement=%r regex=%s",
            self.column,
            self.pattern,
            self.replacement,
            self.regex,
        )

        return replace_values(
            df,
            self.column,
            self.pattern,
            self.replacement,
            regex=self.regex,
        )


@dataclass(frozen=True)
class RemoveValueRule(Rule):
    """Remove rows where a column equals a specific value."""

    value: Any

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove rows matching the configured value."""
        logger.debug(
            "Apply RemoveValueRule: col='%s' value=%r",
            self.column,
            self.value,
        )

        if self.column not in df.columns:
            raise KeyError(f"Column '{self.column}' not found.")

        return df.loc[df[self.column].ne(self.value)].copy()


@dataclass(frozen=True)
class StripRule(Rule):
    """Trim leading and trailing whitespace from a column."""

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """Strip whitespace from the column."""
        logger.debug("Apply StripRule: col='%s'", self.column)

        return clean_text(df, self.column, strip=True)


# =====================================================================
# Rule application
# =====================================================================

def apply_rules(
    df: pd.DataFrame,
    rules: Iterable[Rule],
) -> pd.DataFrame:
    """Apply a sequence of rules to a DataFrame.

    Rules are applied in the order provided. Each rule receives
    the DataFrame produced by the previous rule.

    Args:
        df: Source DataFrame.
        rules: Iterable of Rule objects.

    Returns:
        A new DataFrame after all rules have been applied.
    """
    out = df

    for rule in rules:
        logger.debug("Applying rule: %s", rule)
        out = rule.apply(out)

    return out
