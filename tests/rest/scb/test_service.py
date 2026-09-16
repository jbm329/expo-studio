import pytest

from expo_jbm329.services.rest.scb.service import (
    ScbQueryBuilder,
    ScbQueryError,
    ScbSelection,
)


def test_build_query_includes_value_codes_and_codelists():
    selections = [
        ScbSelection("Region", ("01", "03"), codelist="vs_CKM02Län"),
        ScbSelection("Tid", ("2026M01", "2026M02"), codelist="vs_Manad"),
    ]

    params = ScbQueryBuilder().build(
        table_id="TAB6471",
        selections=selections,
        lang="sv",
    )

    assert params["lang"] == "sv"
    assert params["valueCodes[Region]"] == "01,03"
    assert params["codelist[Region]"] == "vs_CKM02Län"
    assert params["valueCodes[Tid]"] == "2026M01,2026M02"
    assert params["codelist[Tid]"] == "vs_Manad"


def test_build_query_rejects_empty_table_id():
    with pytest.raises(ScbQueryError, match="table id"):
        ScbQueryBuilder().build(table_id=" ", selections=[ScbSelection("Kon", ("1",))])


def test_build_query_rejects_empty_selection_values():
    with pytest.raises(ScbQueryError, match="values"):
        ScbSelection("Alder", (), codelist="vs_Alder")
