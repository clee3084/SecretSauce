import datetime
import json
import os

import numpy as np
import pandas as pd
import pytest
from catboost import CatBoostClassifier
from pandas.testing import assert_frame_equal
from requests_mock.mocker import Mocker
from sklearn.ensemble import RandomForestClassifier

from upgini.features_enricher import FeaturesEnricher
from upgini.errors import ValidationError
from upgini.metadata import (
    SearchKey,
    CVType,
    FeaturesMetadataV2,
    HitRateMetrics,
    ModelEvalSet,
    ProviderTaskMetadataV2,
)
from upgini.normalizer.normalize_utils import Normalizer
from upgini.resource_bundle import bundle
from upgini.search_task import SearchTask
from upgini.utils.datetime_utils import DateTimeSearchKeyConverter

from .utils import (
    mock_default_requests,
    mock_get_metadata,
    mock_get_task_metadata_v2,
    mock_get_task_metadata_v2_from_file,
    mock_initial_progress,
    mock_initial_search,
    mock_initial_summary,
    mock_raw_features,
    mock_target_outliers,
    mock_target_outliers_file,
    mock_validation_progress,
    mock_validation_raw_features,
    mock_validation_search,
    mock_validation_summary,
)

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "test_data/enricher/",
)

segment_header = bundle.get("quality_metrics_segment_header")
train_segment = bundle.get("quality_metrics_train_segment")
eval_1_segment = bundle.get("quality_metrics_eval_segment").format(1)
eval_2_segment = bundle.get("quality_metrics_eval_segment").format(2)
rows_header = bundle.get("quality_metrics_rows_header")
target_mean_header = bundle.get("quality_metrics_mean_target_header")
match_rate_header = bundle.get("quality_metrics_match_rate_header")
baseline_rocauc = bundle.get("quality_metrics_baseline_header").format("roc_auc")
enriched_rocauc = bundle.get("quality_metrics_enriched_header").format("roc_auc")
baseline_gini = bundle.get("quality_metrics_baseline_header").format("GINI")
enriched_gini = bundle.get("quality_metrics_enriched_header").format("GINI")
baseline_rmse = bundle.get("quality_metrics_baseline_header").format("rmse")
enriched_rmse = bundle.get("quality_metrics_enriched_header").format("rmse")
baseline_RMSLE = bundle.get("quality_metrics_baseline_header").format("RMSLE")
enriched_RMSLE = bundle.get("quality_metrics_enriched_header").format("RMSLE")
baseline_mae = bundle.get("quality_metrics_baseline_header").format("mean_absolute_error")
enriched_mae = bundle.get("quality_metrics_enriched_header").format("mean_absolute_error")
uplift = bundle.get("quality_metrics_uplift_header")

SearchTask.PROTECT_FROM_RATE_LIMIT = False
SearchTask.POLLING_DELAY_SECONDS = 0


def test_real_case_metric_binary(requests_mock: Mocker):
    BASE_DIR = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "test_data/",
    )

    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    requests_mock.get(
        url + f"/public/api/v2/search/{search_task_id}/metadata",
        json={
            "fileUploadId": "123",
            "fileMetadataId": "123",
            "name": "test",
            "description": "",
            "columns": [
                {
                    "index": 0,
                    "name": "score",
                    "originalName": "score",
                    "dataType": "INT",
                    "meaningType": "FEATURE",
                },
                {
                    "index": 1,
                    "name": "request_date",
                    "originalName": "request_date",
                    "dataType": "INT",
                    "meaningType": "DATE",
                },
                {"index": 2, "name": "target", "originalName": "target", "dataType": "INT", "meaningType": "DATE"},
                {
                    "index": 3,
                    "name": "system_record_id",
                    "originalName": "system_record_id",
                    "dataType": "INT",
                    "meaningType": "SYSTEM_RECORD_ID",
                },
            ],
            "searchKeys": [["rep_date"]],
            "hierarchicalGroupKeys": [],
            "hierarchicalSubgroupKeys": [],
            "rowsCount": 30505,
        },
    )
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="score",
                    type="numeric",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.368092,
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=10000, hit_rate=1.0, hit_rate_percent=100.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(BASE_DIR, "real_train_df.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    # train = pd.read_parquet(os.path.join(BASE_DIR, "real_train.parquet"))
    # train.sort_index()
    # X = train[["request_date", "score"]]
    # y = train["target1"].rename("target")
    # test = pd.read_parquet(os.path.join(BASE_DIR, "real_test.parquet"))
    # eval_set = [(test[["request_date", "score"]], test["target1"].rename("target"))]

    search_keys = {"request_date": SearchKey.DATE}
    enricher = FeaturesEnricher(
        search_keys=search_keys,
        endpoint=url,
        api_key="fake_api_key",
        date_format="%Y-%m-%d",
        country_code="RU",
        search_id=search_task_id,
        logs_enabled=False,
    )

    train = pd.read_parquet(os.path.join(BASE_DIR, "real_train_df.parquet"))
    enricher.X = train.drop(columns=["system_record_id", "target1"])
    enricher.y = train["target1"]

    test = pd.read_parquet(os.path.join(BASE_DIR, "real_test_df.parquet"))
    enricher.eval_set = [(test.drop(columns=["system_record_id", "target1"]), test["target1"])]

    enriched_X = train.drop(columns="target1")
    sampled_X = enriched_X
    sampled_y = train["target1"]

    enriched_eval_X = test.drop(columns="target1")
    sampled_eval_X = enriched_eval_X
    sampled_eval_y = test["target1"]

    columns_renaming = {c: c for c in enriched_X.columns}

    enricher._FeaturesEnricher__cached_sampled_datasets = (
        sampled_X,
        sampled_y,
        enriched_X,
        {0: (sampled_eval_X, enriched_eval_X, sampled_eval_y)},
        search_keys,
        columns_renaming,
    )

    metrics = enricher.calculate_metrics()
    metrics[baseline_gini] = np.floor(metrics[baseline_gini] * 1000) / 1000
    print(metrics)

    expected_metrics = pd.DataFrame(
        {
            segment_header: [train_segment, eval_1_segment],
            rows_header: [28000, 2505],
            target_mean_header: [0.8825, 0.8854],
            baseline_gini: [0.490, 0.462],
        }
    )

    assert_frame_equal(expected_metrics, metrics)


def test_demo_metrics(requests_mock: Mocker):
    BASE_DIR = os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        "test_data/demo/",
    )

    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    with open(os.path.join(BASE_DIR, "file_meta.json")) as f:
        file_meta = json.load(f)
    requests_mock.get(url + f"/public/api/v2/search/{search_task_id}/metadata", json=file_meta)
    with open(os.path.join(BASE_DIR, "provider_meta.json"), "rb") as f:
        provider_meta_json = json.load(f)
        provider_meta = ProviderTaskMetadataV2.parse_obj(provider_meta_json)
    mock_get_task_metadata_v2(requests_mock, url, ads_search_task_id, provider_meta)
    mock_raw_features(requests_mock, url, search_task_id, os.path.join(BASE_DIR, "x_enriched.parquet"))

    search_keys = {"country": SearchKey.COUNTRY, "Postal_code": SearchKey.POSTAL_CODE}
    enricher = FeaturesEnricher(
        search_keys=search_keys,
        endpoint=url,
        api_key="fake_api_key",
        generate_features=["combined", "company_txt"],
        search_id=search_task_id,
        logs_enabled=False,
    )

    x_sampled = pd.read_parquet(os.path.join(BASE_DIR, "x_sampled.parquet"))
    y_sampled = pd.read_parquet(os.path.join(BASE_DIR, "y_sampled.parquet"))["target"]
    enriched_X = pd.read_parquet(os.path.join(BASE_DIR, "x_enriched.parquet"))

    enricher.X = x_sampled.drop(columns="system_record_id")
    enricher.y = y_sampled
    enricher.eval_set = []

    columns_renaming = {c: c for c in x_sampled.columns}

    enricher._FeaturesEnricher__cached_sampled_datasets = (
        x_sampled,
        y_sampled,
        enriched_X,
        dict(),
        search_keys,
        columns_renaming,
    )

    metrics = enricher.calculate_metrics(scoring="mean_absolute_error")
    print(metrics)

    expected_metrics = pd.DataFrame(
        {
            segment_header: [train_segment],
            rows_header: [464],
            target_mean_header: [100.7802],
            baseline_mae: [21.508906],
            enriched_mae: [20.884132],
            uplift: [0.624774],
        }
    )

    assert_frame_equal(expected_metrics, metrics)


def test_default_metric_binary(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
                FeaturesMetadataV2(
                    name="feature_2_cat", type="categorical", source="etalon", hit_rate=100.0, shap_value=0.0
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    df = pd.read_csv(os.path.join(FIXTURE_DIR, "input.csv"))
    df["feature_2_cat"] = np.random.randint(0, 10, len(df))
    df["feature_2_cat"] = df["feature_2_cat"].astype("string").astype("category")
    df = df.reset_index().rename(columns={"index": "high_cardinality_feature"})
    df["date"] = pd.date_range(datetime.date(2020, 1, 1), periods=len(df))
    df_train = df[0:500]
    X = df_train[["phone", "date", "feature1", "high_cardinality_feature"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "date", "feature1", "high_cardinality_feature"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "date", "feature1", "high_cardinality_feature"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE, "date": SearchKey.DATE},
        endpoint=url,
        api_key="fake_api_key",
        logs_enabled=False,
    )

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    metrics_df = enricher.calculate_metrics()
    assert metrics_df is not None
    print(metrics_df)

    # FIXME: different between python versions
    # assert metrics_df.loc[0, segment_header] == train_segment
    # assert metrics_df.loc[0, rows_header] == 500
    # assert metrics_df.loc[0, target_mean_header] == 0.51
    # assert metrics_df.loc[0, baseline_gini] == approx(0.104954)
    # assert metrics_df.loc[0, enriched_gini] == approx(0.097089)
    # assert metrics_df.loc[0, uplift] == approx(-0.007864)

    # assert metrics_df.loc[1, segment_header] == eval_1_segment
    # assert metrics_df.loc[1, rows_header] == 250
    # assert metrics_df.loc[1, target_mean_header] == 0.452
    # assert metrics_df.loc[1, baseline_gini] == approx(-0.053705)
    # assert metrics_df.loc[1, enriched_gini] == approx(0.080266)
    # assert metrics_df.loc[1, uplift] == approx(0.133971)

    # assert metrics_df.loc[2, segment_header] == eval_2_segment
    # assert metrics_df.loc[2, rows_header] == 250
    # assert metrics_df.loc[2, target_mean_header] == 0.536
    # assert metrics_df.loc[2, baseline_gini] == approx(-0.002072)
    # assert metrics_df.loc[2, enriched_gini] == approx(-0.002432)
    # assert metrics_df.loc[2, uplift] == approx(-0.000360)


def test_default_metric_binary_with_outliers(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    path_to_metadata = os.path.join(FIXTURE_DIR, "metadata_regression_date_country_postal.json")
    mock_get_task_metadata_v2_from_file(
        requests_mock,
        url,
        ads_search_task_id,
        path_to_metadata
    )

    search_keys = {
        "date": SearchKey.DATE,
        "country": SearchKey.COUNTRY,
        "postal_code": SearchKey.POSTAL_CODE
    }
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_regression_date_country_postal.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    df = pd.read_parquet(os.path.join(FIXTURE_DIR, "tds_regression_date_country_postal.parquet"))
    search_keys_copy = search_keys.copy()
    df_with_eval_set_index = df.copy()
    df_with_eval_set_index.loc[df_with_eval_set_index.segment == "train", "eval_set_index"] = 0
    df_with_eval_set_index.loc[df_with_eval_set_index.segment == "oot", "eval_set_index"] = 1
    df_with_eval_set_index.drop(columns="segment")

    mock_features = pd.read_parquet(path_to_mock_features)

    converter = DateTimeSearchKeyConverter("date")
    df_with_eval_set_index_with_date = converter.convert(df_with_eval_set_index)
    search_keys_copy = search_keys.copy()
    normalizer = Normalizer(search_keys_copy, converter.generated_features)
    df_with_eval_set_index_with_date = normalizer.normalize(df_with_eval_set_index_with_date)

    mock_features["system_record_id"] = pd.util.hash_pandas_object(
        df_with_eval_set_index_with_date[sorted(search_keys_copy.keys())].reset_index(drop=True), index=False
    ).astype("float64")
    mock_features["entity_system_record_id"] = mock_features["system_record_id"]
    mock_features = mock_features.drop_duplicates(subset=["entity_system_record_id"], keep="first")
    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)

    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, mock_features)

    target_outliers_path = os.path.join(FIXTURE_DIR, "target_outliers_regression_date_country_postal.parquet")
    target_outliers_id = mock_target_outliers(requests_mock, url, search_task_id)
    mock_target_outliers_file(requests_mock, url, target_outliers_id, target_outliers_path)

    df_train = df.query("segment == 'train'").drop(columns="segment")
    eval_1 = df.query("segment == 'oot'").drop(columns="segment")
    X = df_train.drop(columns="target")
    y = df_train["target"]
    eval_X_1 = eval_1.drop(columns="target")
    eval_y_1 = eval_1["target"]
    eval_set = [(eval_X_1, eval_y_1)]
    enricher = FeaturesEnricher(
        search_keys=search_keys,
        endpoint=url,
        api_key="fake_api_key",
        logs_enabled=False,
    )

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    assert not enriched_X["f_weather_date_weather_umap_42_4ac1a34c"].isna().any()

    metrics_df = enricher.calculate_metrics()
    assert metrics_df is not None
    print(metrics_df)

    expected_metrics = pd.DataFrame({
        "Dataset type": ["Train", "Eval 1"],
        "Rows": [9859, 141],
        "Mean target": [5932.9303, 5773.3232],
        "Baseline mean_squared_error": [6.990707e+06, 5.130514e+06],
        "Enriched mean_squared_error": [6.142263e+06, 4.268262e+06],
        "Uplift": [848444.622588, 862252.445628]
    })

    assert_frame_equal(metrics_df, expected_metrics)


def test_default_metric_binary_custom_loss(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
                FeaturesMetadataV2(
                    name="feature_2_cat", type="categorical", source="etalon", hit_rate=100.0, shap_value=0.0
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    df = pd.read_csv(os.path.join(FIXTURE_DIR, "input.csv"))
    df["feature_2_cat"] = np.random.randint(0, 10, len(df))
    df["feature_2_cat"] = df["feature_2_cat"].astype("string").astype("category")
    df["date"] = pd.date_range(datetime.date(2020, 1, 1), periods=len(df))
    df_train = df[0:500]
    X = df_train[["phone", "date", "feature1"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "date", "feature1"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "date", "feature1"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE, "date": SearchKey.DATE},
        endpoint=url,
        api_key="fake_api_key",
        logs_enabled=False,
        loss="binary",
    )

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    metrics_df = enricher.calculate_metrics()
    assert metrics_df is not None
    print(metrics_df)

    # FIXME: different between python versions
    # assert metrics_df.loc[0, segment_header] == train_segment
    # assert metrics_df.loc[0, rows_header] == 500
    # assert metrics_df.loc[0, target_mean_header] == 0.51
    # assert metrics_df.loc[0, baseline_gini] == approx(0.104954)
    # assert metrics_df.loc[0, enriched_gini] == approx(0.097089)
    # assert metrics_df.loc[0, uplift] == approx(-0.007864)

    # assert metrics_df.loc[1, segment_header] == eval_1_segment
    # assert metrics_df.loc[1, rows_header] == 250
    # assert metrics_df.loc[1, target_mean_header] == 0.452
    # assert metrics_df.loc[1, baseline_gini] == approx(-0.053705)
    # assert metrics_df.loc[1, enriched_gini] == approx(0.080266)
    # assert metrics_df.loc[1, uplift] == approx(0.133971)

    # assert metrics_df.loc[2, segment_header] == eval_2_segment
    # assert metrics_df.loc[2, rows_header] == 250
    # assert metrics_df.loc[2, target_mean_header] == 0.536
    # assert metrics_df.loc[2, baseline_gini] == approx(-0.002072)
    # assert metrics_df.loc[2, enriched_gini] == approx(-0.002432)
    # assert metrics_df.loc[2, uplift] == approx(-0.000360)


def test_default_metric_binary_shuffled(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
                FeaturesMetadataV2(
                    name="feature_2_cat", type="categorical", source="etalon", hit_rate=100.0, shap_value=0.0
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    df = pd.read_csv(os.path.join(FIXTURE_DIR, "input.csv"))
    df["feature_2_cat"] = np.random.randint(0, 10, len(df))
    df["feature_2_cat"] = df["feature_2_cat"].astype("string").astype("category")
    df["date"] = pd.date_range(datetime.date(2020, 1, 1), periods=len(df))
    df_train = df[0:500]
    df_train = df_train.sample(frac=1)
    X = df_train[["phone", "date", "feature1"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_1 = eval_1.sample(frac=1)
    eval_2 = df[750:1000]
    eval_2 = eval_2.sample(frac=1)
    eval_X_1 = eval_1[["phone", "date", "feature1"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "date", "feature1"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE, "date": SearchKey.DATE},
        endpoint=url,
        api_key="fake_api_key",
        logs_enabled=False,
    )

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    metrics_df = enricher.calculate_metrics()
    assert metrics_df is not None
    print(metrics_df)

    # FIXME: different between python versions
    # assert metrics_df.loc[0, segment_header] == train_segment
    # assert metrics_df.loc[0, rows_header] == 500
    # assert metrics_df.loc[0, target_mean_header] == 0.51
    # assert metrics_df.loc[0, baseline_gini] == approx(0.104954)
    # assert metrics_df.loc[0, enriched_gini] == approx(0.097089)
    # assert metrics_df.loc[0, uplift] == approx(-0.007864)

    # assert metrics_df.loc[1, segment_header] == eval_1_segment
    # assert metrics_df.loc[1, rows_header] == 250
    # assert metrics_df.loc[1, target_mean_header] == 0.452
    # assert metrics_df.loc[1, baseline_gini] == approx(-0.053705)
    # assert metrics_df.loc[1, enriched_gini] == approx(0.080266)
    # assert metrics_df.loc[1, uplift] == approx(0.133971)

    # assert metrics_df.loc[2, segment_header] == eval_2_segment
    # assert metrics_df.loc[2, rows_header] == 250
    # assert metrics_df.loc[2, target_mean_header] == 0.536
    # assert metrics_df.loc[2, baseline_gini] == approx(-0.002072)
    # assert metrics_df.loc[2, enriched_gini] == approx(-0.002432)
    # assert metrics_df.loc[2, uplift] == approx(-0.000360)


def test_blocked_timeseries_rmsle(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    # TODO replace with input dataset with date search key and regression target
    df = pd.read_csv(os.path.join(FIXTURE_DIR, "input.csv"))
    df_train = df[0:500]
    X = df_train[["phone", "feature1"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "feature1"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "feature1"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE},
        endpoint=url,
        api_key="fake_api_key",
        cv=CVType.blocked_time_series,
        logs_enabled=False,
    )

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    metrics_df = enricher.calculate_metrics(scoring="RMSLE")
    assert metrics_df is not None
    print(metrics_df)

    assert metrics_df.loc[0, segment_header] == train_segment
    assert metrics_df.loc[0, rows_header] == 500
    assert metrics_df.loc[0, target_mean_header] == 0.51
    assert metrics_df.loc[0, baseline_RMSLE] == approx(0.457746)
    assert metrics_df.loc[0, enriched_RMSLE] == approx(0.463769)
    assert metrics_df.loc[0, uplift] == approx(-0.006023)

    assert metrics_df.loc[1, segment_header] == eval_1_segment
    assert metrics_df.loc[1, rows_header] == 250
    assert metrics_df.loc[1, target_mean_header] == 0.452
    assert metrics_df.loc[1, baseline_RMSLE] == approx(0.501729)
    assert metrics_df.loc[1, enriched_RMSLE] == approx(0.480895)
    assert metrics_df.loc[1, uplift] == approx(0.020834)

    assert metrics_df.loc[2, segment_header] == eval_2_segment
    assert metrics_df.loc[2, rows_header] == 250
    assert metrics_df.loc[2, target_mean_header] == 0.536
    assert metrics_df.loc[2, baseline_RMSLE] == approx(0.492452)
    assert metrics_df.loc[2, enriched_RMSLE] == approx(0.495043)
    assert metrics_df.loc[2, uplift] == approx(-0.002591)


def test_catboost_metric_binary(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    df = pd.read_csv(os.path.join(FIXTURE_DIR, "input.csv"))
    df_train = df[0:500]
    X = df_train[["phone", "feature1"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "feature1"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "feature1"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE}, endpoint=url, api_key="fake_api_key", logs_enabled=False
    )

    with pytest.raises(ValidationError, match=bundle.get("metrics_unfitted_enricher")):
        enricher.calculate_metrics()

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    estimator = CatBoostClassifier(random_seed=42, verbose=False)
    metrics_df = enricher.calculate_metrics(estimator=estimator, scoring="roc_auc")
    assert metrics_df is not None
    print(metrics_df)

    if pd.__version__ >= "2.2.0":
        expected_metrics = pd.DataFrame({
            segment_header: [train_segment, eval_1_segment, eval_2_segment],
            rows_header: [500, 250, 250],
            target_mean_header: [0.51, 0.452, 0.536],
            baseline_gini: [0.038535, -0.042865, 0.005713],
            enriched_gini: [0.083988, -0.013009, -0.050579],
            uplift: [0.045453, 0.029856, -0.056292]
        })
    elif pd.__version__ >= "2.1.0":
        expected_metrics = pd.DataFrame({
            segment_header: [train_segment, eval_1_segment, eval_2_segment],
            rows_header: [500, 250, 250],
            target_mean_header: [0.51, 0.452, 0.536],
            baseline_gini: [0.034462, -0.043951, 0.002483],
            enriched_gini: [-0.005404, 0.033900, -0.016109],
            uplift: [-0.039866, 0.077850, -0.018592]
        })
    else:
        pass

    assert_frame_equal(metrics_df, expected_metrics, atol=10**-6)


def test_catboost_metric_binary_with_cat_features(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="ads",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="cat_feature2",
                    type="categorical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.2,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    df = pd.read_parquet(os.path.join(FIXTURE_DIR, "input_with_cat.parquet"))
    df_train = df[0:500]
    X = df_train[["phone", "country", "feature1", "cat_feature2"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "country", "feature1", "cat_feature2"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "country", "feature1", "cat_feature2"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE, "country": SearchKey.COUNTRY},
        endpoint=url,
        api_key="fake_api_key",
        logs_enabled=False,
    )

    with pytest.raises(ValidationError, match=bundle.get("metrics_unfitted_enricher")):
        enricher.calculate_metrics()

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    estimator = CatBoostClassifier(random_seed=42, verbose=False, cat_features=[1, 3])
    metrics_df = enricher.calculate_metrics(estimator=estimator, scoring="roc_auc")
    assert metrics_df is not None
    print(metrics_df)

    expected_metrics = pd.DataFrame({
        segment_header: [train_segment, eval_1_segment, eval_2_segment],
        rows_header: [500, 250, 250],
        target_mean_header: [0.51, 0.452, 0.536],
        baseline_gini: [0.121477, -0.051043, -0.000618],
        enriched_gini: [0.127284, -0.006292, -0.027277],
        uplift: [0.005807, 0.044752, -0.026660]
    })

    assert_frame_equal(metrics_df, expected_metrics, atol=10**-6)


@pytest.mark.skip
def test_lightgbm_metric_binary(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="ads",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_features)

    df = pd.read_csv(os.path.join(FIXTURE_DIR, "input.csv"))
    df_train = df[0:500]
    X = df_train[["phone", "feature1"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "feature1"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "feature1"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE},
        endpoint=url,
        api_key="fake_api_key",
        logs_enabled=False,
    )

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    #     with pytest.raises(ValidationError, match=r".*mean_absolute_persentage_error is not a valid scoring value.*"):
    with pytest.raises(ValidationError, match=r"mean_absolute_persentage_error is not a valid scoring value."):
        enricher.calculate_metrics(scoring="mean_absolute_persentage_error")

    assert len(enriched_X) == len(X)

    from lightgbm import LGBMClassifier  # type: ignore

    estimator = LGBMClassifier(random_seed=42)
    metrics_df = enricher.calculate_metrics(estimator=estimator, scoring="mean_absolute_error")
    assert metrics_df is not None
    pd.set_option("display.max_columns", 1000)
    print(metrics_df)

    expected_metrics = pd.DataFrame({
        segment_header: [train_segment, eval_1_segment, eval_2_segment],
        rows_header: [500, 250, 250],
        target_mean_header: [0.51, 0.452, 0.536],
        baseline_mae: [0.5040, 0.4776, 0.4872],
        enriched_mae: [0.4260, 0.4720, 0.5056],
        uplift: [0.0780, 0.0056, -0.0184]
    })

    assert_frame_equal(metrics_df, expected_metrics, atol=10**-6)


def test_rf_metric_rmse(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    df = pd.read_csv(os.path.join(FIXTURE_DIR, "input.csv"))
    df_train = df[0:500]
    X = df_train[["phone", "feature1"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "feature1"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "feature1"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE}, endpoint=url, api_key="fake_api_key", logs_enabled=False
    )

    with pytest.raises(ValidationError, match=bundle.get("metrics_unfitted_enricher")):
        enricher.calculate_metrics()

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    estimator = RandomForestClassifier(random_state=42)
    metrics_df = enricher.calculate_metrics(estimator=estimator, scoring="rmse")
    assert metrics_df is not None
    print(metrics_df)

    if pd.__version__ >= "2.2.0":
        expected_metrics = pd.DataFrame({
            segment_header: [train_segment, eval_1_segment, eval_2_segment],
            rows_header: [500, 250, 250],
            target_mean_header: [0.51, 0.452, 0.536],
            baseline_rmse: [0.693845, 0.717754, 0.682288],
            enriched_rmse: [0.700793, 0.700747, 0.702545],
            uplift: [-0.006948, 0.017007, -0.020257]
        })
    elif pd.__version__ >= "2.1.0":
        expected_metrics = pd.DataFrame({
            segment_header: [train_segment, eval_1_segment, eval_2_segment],
            rows_header: [500, 250, 250],
            target_mean_header: [0.51, 0.452, 0.536],
            baseline_rmse: [0.716437, 0.723843, 0.679943],
            enriched_rmse: [0.712200, 0.697399, 0.693871],
            uplift: [0.004236, 0.026444, -0.013928]
        })
    else:
        pass

    assert_frame_equal(metrics_df, expected_metrics, atol=10**-6)


def test_default_metric_binary_with_string_feature(requests_mock: Mocker):
    url = "http://fake_url2"
    mock_default_requests(requests_mock, url)
    search_task_id = mock_initial_search(requests_mock, url)
    mock_initial_progress(requests_mock, url, search_task_id)
    ads_search_task_id = mock_initial_summary(
        requests_mock,
        url,
        search_task_id,
    )
    mock_get_metadata(requests_mock, url, search_task_id)
    mock_get_task_metadata_v2(
        requests_mock,
        url,
        ads_search_task_id,
        ProviderTaskMetadataV2(
            features=[
                FeaturesMetadataV2(
                    name="ads_feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=99.0,
                    shap_value=10.1,
                ),
                FeaturesMetadataV2(
                    name="feature1",
                    type="numerical",
                    source="etalon",
                    hit_rate=100.0,
                    shap_value=0.1,
                ),
                FeaturesMetadataV2(
                    name="feature_2_cat", type="categorical", source="etalon", hit_rate=100.0, shap_value=0.01
                ),
            ],
            hit_rate_metrics=HitRateMetrics(
                etalon_row_count=10000, max_hit_count=9900, hit_rate=0.99, hit_rate_percent=99.0
            ),
            eval_set_metrics=[
                ModelEvalSet(
                    eval_set_index=1,
                    hit_rate=1.0,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=1000, hit_rate=1.0, hit_rate_percent=100.0
                    ),
                ),
                ModelEvalSet(
                    eval_set_index=2,
                    hit_rate=0.99,
                    hit_rate_metrics=HitRateMetrics(
                        etalon_row_count=1000, max_hit_count=990, hit_rate=0.99, hit_rate_percent=99.0
                    ),
                ),
            ],
        ),
    )
    path_to_mock_features = os.path.join(FIXTURE_DIR, "features_with_entity_system_record_id.parquet")
    mock_raw_features(requests_mock, url, search_task_id, path_to_mock_features)

    validation_search_task_id = mock_validation_search(requests_mock, url, search_task_id)
    mock_validation_progress(requests_mock, url, validation_search_task_id)
    mock_validation_summary(
        requests_mock,
        url,
        search_task_id,
        ads_search_task_id,
        validation_search_task_id,
    )
    path_to_mock_validation_features = os.path.join(
        FIXTURE_DIR, "validation_features_with_entity_system_record_id.parquet"
    )
    mock_validation_raw_features(requests_mock, url, validation_search_task_id, path_to_mock_validation_features)

    df = pd.read_parquet(os.path.join(FIXTURE_DIR, "input_with_string_feature.parquet"))
    df_train = df[0:500]
    X = df_train[["phone", "feature1", "feature_2_cat"]]
    y = df_train["target"]
    eval_1 = df[500:750]
    eval_2 = df[750:1000]
    eval_X_1 = eval_1[["phone", "feature1", "feature_2_cat"]]
    eval_y_1 = eval_1["target"]
    eval_X_2 = eval_2[["phone", "feature1", "feature_2_cat"]]
    eval_y_2 = eval_2["target"]
    eval_set = [(eval_X_1, eval_y_1), (eval_X_2, eval_y_2)]
    enricher = FeaturesEnricher(
        search_keys={"phone": SearchKey.PHONE}, endpoint=url, api_key="fake_api_key", logs_enabled=False
    )

    enriched_X = enricher.fit_transform(X, y, eval_set, calculate_metrics=False)

    assert len(enriched_X) == len(X)

    metrics_df = enricher.calculate_metrics()
    assert metrics_df is not None
    print(metrics_df)

    if pd.__version__ >= "2.2.0":
        expected_metrics = pd.DataFrame({
            segment_header: [train_segment, eval_1_segment, eval_2_segment],
            rows_header: [500, 250, 250],
            target_mean_header: [0.51, 0.452, 0.536],
            baseline_gini: [0.062187, -0.068458, -0.011065],
            enriched_gini: [0.017183, -0.054609, -0.057643],
            uplift: [-0.045005, 0.013849, -0.046577]
        })
    elif pd.__version__ >= "2.1.0":
        expected_metrics = pd.DataFrame({
            segment_header: [train_segment, eval_1_segment, eval_2_segment],
            rows_header: [500, 250, 250],
            target_mean_header: [0.51, 0.452, 0.536],
            baseline_gini: [0.032605, -0.014198, -0.042730],
            enriched_gini: [0.021616, -0.029843, -0.010859],
            uplift: [-0.010989, -0.015645, 0.031871]
        })
    else:
        pass

    assert_frame_equal(metrics_df, expected_metrics, atol=10**-6)


def approx(value: float):
    return pytest.approx(value, abs=0.000001)
