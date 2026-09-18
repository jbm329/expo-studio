"""Internal helpers for data operations."""
import pandas as pd


def drop_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Internal helper: drop a column by name."""
    if column not in df.columns:
        raise KeyError(f"Column '{column}' not found.")
    return df.drop(columns=[column])
