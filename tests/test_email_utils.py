import pandas as pd
from pandas.testing import assert_frame_equal

from upgini.metadata import SearchKey
from upgini.utils.email_utils import EmailSearchKeyConverter, EmailSearchKeyDetector

detector = EmailSearchKeyDetector()


def test_email_search_key_detection_by_name():
    df = pd.DataFrame({"email": ["123", "321", "555"]})

    assert detector.get_search_key_column(df) == "email"

    df = pd.DataFrame({"e-mail": ["123", "321", "555"]})

    assert detector.get_search_key_column(df) == "e-mail"

    df = pd.DataFrame({"e_mail": ["123", "321", "555"]})

    assert detector.get_search_key_column(df) == "e_mail"


def test_email_search_key_detection_by_values():
    df = pd.DataFrame({"eml": ["asdf@asdf.sad", "woei@skdjfh.fnj"] + ["12@3"] * 8})

    assert detector.get_search_key_column(df) == "eml"

    df = pd.DataFrame({"eml": ["asdf@asdf.sad"] + ["12@3"] * 9})

    assert detector.get_search_key_column(df) is None

    df = pd.DataFrame({"eml": [1, 2, 3, 4, 5]})

    assert detector.get_search_key_column(df) is None


def test_convertion_to_hem():
    df = pd.DataFrame({"email": ["test@google.com", "", "@", None, 0.0]})

    search_keys = {"email": SearchKey.EMAIL}
    converter = EmailSearchKeyConverter("email", None, search_keys)
    df = converter.convert(df)

    assert search_keys == {"generated_hem": SearchKey.HEM}

    expected_df = pd.DataFrame(
        {
            "generated_hem": [
                "8b0080a904da73e6e500ada3d09a88037289b5c08e03d3a09546ffacc5b5fd57",
                None,
                None,
                None,
                None,
            ],
            "email_domain": ["google.com", None, None, None, None],
        }
    )

    assert_frame_equal(expected_df, df)

    assert df["email_domain"].astype("string").isnull().sum() == 4


def test_convertion_to_hem_with_existing_hem():
    df = pd.DataFrame(
        {
            "email": ["test@google.com", "", None, 0.0],
            "hem": ["8b0080a904da73e6e500ada3d09a88037289b5c08e03d3a09546ffacc5b5fd57", None, None, None],
        }
    )

    search_keys = {"email": SearchKey.EMAIL, "hem": SearchKey.HEM}
    converter = EmailSearchKeyConverter("email", "hem", search_keys)
    df = converter.convert(df)

    assert search_keys == {"hem": SearchKey.HEM}

    expected_df = pd.DataFrame(
        {
            "hem": ["8b0080a904da73e6e500ada3d09a88037289b5c08e03d3a09546ffacc5b5fd57", None, None, None],
            "email_domain": ["google.com", None, None, None],
        }
    )

    assert_frame_equal(expected_df, df)
