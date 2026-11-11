from __future__ import annotations

from typing import TYPE_CHECKING
from xml.etree import ElementTree
from zipfile import ZipFile

import pandas as pd
import pytest
from openpyxl import Workbook

from expo_jbm329.services.file_loader import FileLoader, OperationCancelledError

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def loader() -> FileLoader:
    return FileLoader()


@pytest.mark.parametrize("batch_size", [1, 100])
@pytest.mark.parametrize("sheet", [None, 0, "Data"])
def test_xlsx_missing_only_nullable_cell_types(
    tmp_path: Path, loader: FileLoader, batch_size: int, sheet: int | str | None
) -> None:
    path = tmp_path / "nullable.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = "Data"
    worksheet.append(["integer", "flag", "complete", "complete_flag", "float", "text", "empty", "date", "mixed"])
    worksheet.append([1, True, 1, True, 1.25, "001", None, pd.Timestamp("2024-01-01"), 1])
    worksheet.append([None, None, 2, False, None, None, None, None, "word"])
    worksheet.append([2, False, 3, True, 2.5, "NA", None, pd.Timestamp("2024-01-02"), None])
    workbook.save(path)
    workbook.close()
    loader.reload_settings({"excel": {"chunk_size_rows": batch_size}})
    progress: list[int] = []

    frame = loader.load_df_auto(str(path), sheet_name=sheet, progress_cb=progress.append, cancel_cb=lambda: False)

    assert frame.dtypes.astype(str).to_dict() == {
        "integer": "Int64",
        "flag": "boolean",
        "complete": "int64",
        "complete_flag": "bool",
        "float": "float64",
        "text": "object",
        "empty": "object",
        "date": "datetime64[ns]",
        "mixed": "object",
    }
    assert frame["integer"].dropna().tolist() == [1, 2]
    assert frame["flag"].dropna().tolist() == [True, False]
    assert frame["text"].tolist() == ["001", None, "NA"]
    assert frame["empty"].isna().all()
    assert frame["mixed"].tolist() == [1, "word", None]
    assert progress[0] == 0 and progress[-1] == 100


@pytest.mark.parametrize("index_col", [0, "id"])
def test_xlsx_nullable_index_and_duplicate_headers(tmp_path: Path, loader: FileLoader, index_col: int | str) -> None:
    path = tmp_path / "index.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(["id", "same", "same"])
    worksheet.append([1, True, 1])
    worksheet.append([None, None, None])
    worksheet.append([2, False, 2])
    workbook.save(path)
    workbook.close()

    frame = loader.load_df_auto(str(path), index_col=index_col)

    assert frame.columns.tolist() == ["same", "same"]
    assert frame.dtypes.astype(str).tolist() == ["boolean", "Int64"]
    pd.testing.assert_index_equal(frame.index, pd.Index(pd.array([1, None, 2], dtype="Int64"), name="id"))


def test_xlsx_loading_cancellation_is_explicit(tmp_path: Path, loader: FileLoader) -> None:
    path = tmp_path / "cancel.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(["value"])
    for value in range(5):
        worksheet.append([value])
    workbook.save(path)
    workbook.close()
    cancelled = False

    def progress(value: int) -> None:
        nonlocal cancelled
        if value > 0:
            cancelled = True

    with pytest.raises(OperationCancelledError):
        loader.load_df_auto(str(path), progress_cb=progress, cancel_cb=lambda: cancelled)


@pytest.mark.parametrize("large", [2**53 + 1, 2**63 - 1, 2**64 - 1])
def test_xlsx_preserves_exact_stored_integer_tokens(tmp_path: Path, loader: FileLoader, large: int) -> None:
    source = tmp_path / "template.xlsx"
    path = tmp_path / "exact.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.append(["value", "other"])
    worksheet.append([1, "large"])
    worksheet.append([None, "missing"])
    worksheet.append([2, "small"])
    workbook.save(source)
    workbook.close()
    # Workbook writers may round large numbers before loading is tested.
    # Store an exact integer token in the XLSX XML to isolate reader precision.
    with ZipFile(source) as original, ZipFile(path, "w") as modified:
        for entry in original.infolist():
            content = original.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                root = ElementTree.fromstring(content)
                namespace = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                cell_value = root.find(".//s:c[@r='A2']/s:v", namespace)
                assert cell_value is not None
                cell_value.text = str(large)
                content = ElementTree.tostring(root)
            modified.writestr(entry, content)

    frame = loader.load_df_auto(str(path))

    assert str(frame["value"].dtype) == ("Int64" if large <= 2**63 - 1 else "UInt64")
    assert frame["value"].dropna().tolist() == [large, 2]
    assert frame["value"].isna().tolist() == [False, True, False]


@pytest.mark.parametrize("headers", [[], ["value", "flag"]])
def test_xlsx_empty_and_header_only_workbooks(tmp_path: Path, loader: FileLoader, headers: list[str]) -> None:
    path = tmp_path / "empty.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    if headers:
        worksheet.append(headers)
    workbook.save(path)
    workbook.close()

    frame = loader.load_df_auto(str(path))

    assert frame.empty
    assert frame.columns.tolist() == headers


def test_xlsx_invalid_sheet_still_fails(tmp_path: Path, loader: FileLoader) -> None:
    path = tmp_path / "sheet.xlsx"
    workbook = Workbook()
    workbook.save(path)
    workbook.close()

    with pytest.raises(ValueError, match="Sheet name not found"):
        loader.load_df_auto(str(path), sheet_name="missing")


def test_excel_raw_cell_builder_preserves_float_intent_and_unsupported_ranges() -> None:
    data: list[list[object]] = [[1.0, 2**64, -1], [None, None, 2**63], [2.0, 1, None]]
    frame = FileLoader._dataframe_from_excel_cells(
        data, ["float", "too_large", "mixed_range"], check_cancel=lambda: None
    )

    assert frame.dtypes.astype(str).tolist() == ["float64", "object", "object"]
    assert frame["float"].dropna().tolist() == [1.0, 2.0]
    assert frame["too_large"].tolist() == [2**64, None, 1]
    assert frame["mixed_range"].tolist() == [-1, 2**63, None]


def test_excel_raw_cell_builder_checks_cancellation() -> None:
    def cancel() -> None:
        raise OperationCancelledError("cancelled")

    with pytest.raises(OperationCancelledError):
        FileLoader._dataframe_from_excel_cells([[1], [None]], ["value"], check_cancel=cancel)


def test_load_df_auto_reads_csv(tmp_path: Path, loader: FileLoader) -> None:
    path = tmp_path / "test.csv"
    pd.DataFrame({"A": [1, 2]}).to_csv(path, index=False)

    df = loader.load_df_auto(str(path))

    assert df.shape[0] == 2
    assert df.shape[1] >= 1


def test_load_df_auto_rejects_unknown_suffix(tmp_path: Path, loader: FileLoader) -> None:
    path = tmp_path / "test.xyz"
    path.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported file format"):
        loader.load_df_auto(str(path))


def test_load_df_auto_can_be_cancelled_before_read(tmp_path: Path, loader: FileLoader) -> None:
    path = tmp_path / "test.csv"
    pd.DataFrame({"A": [1]}).to_csv(path, index=False)

    with pytest.raises(OperationCancelledError):
        loader.load_df_auto(str(path), cancel_cb=lambda: True)


def test_load_df_auto_sets_index_col(tmp_path: Path, loader: FileLoader) -> None:
    path = tmp_path / "test.json"
    pd.DataFrame({"id": [1, 2], "value": [10, 20]}).to_json(path, orient="records")

    df = loader.load_df_auto(str(path), index_col="id")

    assert list(df.index) == [1, 2]
    assert list(df.columns) == ["value"]


@pytest.mark.parametrize("chunk_size", [0, 1, 2, 100])
def test_csv_missing_integer_and_boolean_storage(tmp_path: Path, loader: FileLoader, chunk_size: int) -> None:
    path = tmp_path / "nullable.csv"
    path.write_text(
        "integer,flag,complete_integer,complete_flag,decimal,text,empty\n"
        ",,1,True,1.0,a,\n"
        "9007199254740993,True,2,False,2.0,b,\n"
        "9007199254740992,False,3,True,,,\n",
        encoding="utf-8",
    )
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size, "sniff_delimiter": False, "default_sep": ","}})

    frame = loader.load_df_auto(str(path))

    assert frame.dtypes.astype(str).to_dict() == {
        "integer": "Int64",
        "flag": "boolean",
        "complete_integer": "int64",
        "complete_flag": "bool",
        "decimal": "float64",
        "text": "object",
        "empty": "float64",
    }
    assert frame["integer"].iloc[1:].tolist() == [9007199254740993, 9007199254740992]
    assert frame["flag"].iloc[1:].tolist() == [True, False]
    assert frame["integer"].isna().tolist() == [True, False, False]
    assert frame["decimal"].iloc[:2].tolist() == [1.0, 2.0]
    assert frame["empty"].isna().all()
    assert frame["text"].iloc[:2].tolist() == ["a", "b"]
    assert pd.isna(frame["text"].iloc[2])


@pytest.mark.parametrize("chunk_size", [0, 1, 2, 100])
@pytest.mark.parametrize(
    ("values", "dtype"),
    [
        (["True", "", "False"], "boolean"),
        (["", "True", "False"], "boolean"),
        (["True", "False", ""], "boolean"),
        (["1", "", "2"], "Int64"),
        (["1.0", "", "2.0"], "float64"),
        (["1", "", "2.5"], "float64"),
        (["0", "", "1"], "Int64"),
        (["", "", ""], "float64"),
        (["1", "", "word"], "object"),
        (["True", "", "word"], "object"),
        (["18446744073709551615", "", "18446744073709551614"], "UInt64"),
    ],
)
def test_csv_inference_across_chunks(
    tmp_path: Path, loader: FileLoader, chunk_size: int, values: list[str], dtype: str
) -> None:
    path = tmp_path / "chunks.csv"
    path.write_text("value,other\n" + "".join(f"{value},row\n" for value in values), encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size, "sniff_delimiter": False, "default_sep": ","}})

    frame = loader.load_df_auto(str(path))

    assert str(frame["value"].dtype) == dtype
    assert frame["value"].isna().tolist() == [value == "" for value in values]
    if dtype == "UInt64":
        assert frame["value"].dropna().tolist() == [int(value) for value in values if value]


@pytest.mark.parametrize("chunk_size", [0, 1])
def test_csv_header_only_preserves_empty_schema(tmp_path: Path, loader: FileLoader, chunk_size: int) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("value,flag\n", encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size, "sniff_delimiter": False, "default_sep": ","}})

    frame = loader.load_df_auto(str(path))

    assert frame.empty
    assert frame.columns.tolist() == ["value", "flag"]


def test_csv_nullable_loading_progress_and_cancellation(tmp_path: Path, loader: FileLoader) -> None:
    path = tmp_path / "cancel.csv"
    path.write_text("value,flag\n1,True\n,\n2,False\n", encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": 1, "sniff_delimiter": False, "default_sep": ","}})
    progress: list[int] = []
    cancelled = False

    def on_progress(value: int) -> None:
        nonlocal cancelled
        progress.append(value)
        if value > 0:
            cancelled = True

    with pytest.raises(OperationCancelledError):
        loader.load_df_auto(str(path), progress_cb=on_progress, cancel_cb=lambda: cancelled)
    assert progress[0] == 0

    progress.clear()
    frame = loader.load_df_auto(str(path), progress_cb=progress.append, cancel_cb=lambda: False)
    assert str(frame["value"].dtype) == "Int64"
    assert str(frame["flag"].dtype) == "boolean"
    assert progress[0] == 0 and progress[-1] == 100


@pytest.mark.parametrize("chunk_size", [0, 1, 2, 100])
@pytest.mark.parametrize("missing_token", ["", "NA", "NULL", "NaN", "N/A"])
def test_csv_unsigned_boundary_with_small_values_and_missing_tokens(
    tmp_path: Path, loader: FileLoader, chunk_size: int, missing_token: str
) -> None:
    path = tmp_path / "unsigned.csv"
    path.write_text(f"value,other\n18446744073709551615,row\n{missing_token},row\n1,row\n", encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size, "sniff_delimiter": False, "default_sep": ","}})

    frame = loader.load_df_auto(str(path))

    assert str(frame["value"].dtype) == "UInt64"
    assert frame["value"].dropna().tolist() == [18446744073709551615, 1]
    assert frame["value"].isna().tolist() == [False, True, False]


@pytest.mark.parametrize("chunk_size", [0, 1, 2, 100])
def test_csv_complete_unsigned_values_remain_native(tmp_path: Path, loader: FileLoader, chunk_size: int) -> None:
    path = tmp_path / "complete_unsigned.csv"
    path.write_text("value,other\n18446744073709551615,row\n1,row\n", encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size, "sniff_delimiter": False, "default_sep": ","}})

    frame = loader.load_df_auto(str(path))

    assert str(frame["value"].dtype) == "uint64"
    assert frame["value"].tolist() == [18446744073709551615, 1]


@pytest.mark.parametrize("chunk_size", [0, 1])
@pytest.mark.parametrize("other", ["word", "-1", "18446744073709551616", "9" * 5000])
def test_csv_unsigned_recovery_does_not_coerce_unsupported_values(
    tmp_path: Path, loader: FileLoader, chunk_size: int, other: str
) -> None:
    path = tmp_path / "mixed_unsigned.csv"
    path.write_text(f"value,other\n18446744073709551615,row\n{other},row\n", encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size, "sniff_delimiter": False, "default_sep": ","}})

    frame = loader.load_df_auto(str(path))

    assert str(frame["value"].dtype) == "object"
    assert [str(value) for value in frame["value"]] == ["18446744073709551615", other]
    assert not frame["value"].isna().any()


@pytest.mark.parametrize("index_col", [0, "id"])
def test_csv_direct_index_preserves_native_storage(tmp_path: Path, loader: FileLoader, index_col: int | str) -> None:
    path = tmp_path / "index.csv"
    path.write_text("id,value\n1,10\n2,\n", encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": 0, "sniff_delimiter": False, "default_sep": ","}})

    frame = loader.load_df_auto(str(path), index_col=index_col)

    pd.testing.assert_index_equal(frame.index, pd.Index([1, 2], name="id"))
    assert frame.columns.tolist() == ["value"]
    assert str(frame["value"].dtype) == "Int64"


@pytest.mark.parametrize("chunk_size", [0, 1, 100])
def test_csv_delimiter_quoting_and_missing_tokens_are_preserved(
    tmp_path: Path, loader: FileLoader, chunk_size: int
) -> None:
    path = tmp_path / "quoted.csv"
    path.write_text('value;flag;text\n1;True;"a;b"\nNA;NULL;"quoted ""text"""\n2;False;end\n', encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size}})

    frame = loader.load_df_auto(str(path))

    assert str(frame["value"].dtype) == "Int64"
    assert str(frame["flag"].dtype) == "boolean"
    assert frame["value"].isna().tolist() == [False, True, False]
    assert frame["flag"].isna().tolist() == [False, True, False]
    assert frame["text"].tolist() == ["a;b", 'quoted "text"', "end"]


@pytest.mark.parametrize("chunk_size", [0, 1, 100])
def test_csv_empty_file_still_raises(tmp_path: Path, loader: FileLoader, chunk_size: int) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    loader.reload_settings({"csv": {"read_chunk_size_rows": chunk_size, "sniff_delimiter": False, "default_sep": ","}})

    with pytest.raises(pd.errors.EmptyDataError):
        loader.load_df_auto(str(path))
