"""Internal helpers for data operations."""
import pandas as pd


def drop_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Internal helper: drop a column by name."""
    if column not in df.columns:
        msg = f"Column '{column}' not found."
        raise KeyError(msg)
    return df.drop(columns=[column])
