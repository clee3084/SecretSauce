import os

import pandas as pd
import pytest

from upgini.dataset import Dataset
from upgini.ads import FileColumnMeaningType
from upgini.utils.datetime_utils import DateTimeSearchKeyConverter

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "test_data/categorical/",
)


@pytest.fixture
def etalon_definition():
    return {
        "phone_num": FileColumnMeaningType.MSISDN,
        "rep_date": FileColumnMeaningType.DATE,
        "target": FileColumnMeaningType.TARGET,
    }


@pytest.fixture
def etalon_search_keys():
    return [("phone_num", "rep_date")]


@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "data.csv.gz"))
def test_categorical_dataset(datafiles, etalon_definition, etalon_search_keys):
    df = pd.read_csv(datafiles / "data.csv.gz")
    df = df.reset_index().rename(columns={"index": "system_record_id"})
    converter = DateTimeSearchKeyConverter("rep_date")
    df = converter.convert(df)
    ds = Dataset(
        dataset_name="test Dataset",  # type: ignore
        description="test",  # type: ignore
        df=df,  # type: ignore
        meaning_types=etalon_definition,  # type: ignore
        search_keys=etalon_search_keys,  # type: ignore
    )
    ds.columns_renaming = {c: c for c in df.columns}
    ds.validate()
    expected_valid_rows = 16913
    assert len(ds) == expected_valid_rows
