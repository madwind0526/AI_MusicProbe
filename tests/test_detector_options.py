import pytest

from probe import detector_options as options
from probe.detectors import DETECTORS


def test_detector_registry_and_option_schema_stay_in_sync() -> None:
    # A detector registered without a schema entry would make for_detector()
    # raise at analysis time, long after the mistake was made.
    assert set(DETECTORS) == set(options.DETECTOR_SCHEMA)


def test_implemented_detectors_are_a_subset_of_the_registry() -> None:
    assert options.IMPLEMENTED_DETECTORS <= set(DETECTORS)


def test_implemented_detectors_default_to_counting_toward_the_total() -> None:
    normalized = options.normalize({})["detectors"]

    for name in sorted(options.IMPLEMENTED_DETECTORS):
        assert normalized[name]["includedInTotal"] is True, (
            f"{name} is implemented but defaults to excluded, so its weight is treated as 0"
        )


def test_unimplemented_detectors_default_to_excluded() -> None:
    normalized = options.normalize({})["detectors"]

    for name in sorted(set(DETECTORS) - options.IMPLEMENTED_DETECTORS):
        assert normalized[name]["includedInTotal"] is False


def test_unimplemented_detector_cannot_satisfy_the_weighted_geometric_guard(tmp_path, monkeypatch) -> None:
    # The guard needs at least one implemented detector with a positive weight.
    # attribution is never implemented, so a positive weight on it must not be
    # enough to pass, otherwise the Total would combine nothing.
    target = tmp_path / "detector-options.json"
    monkeypatch.setattr(options, "OPTIONS_PATH", target)

    with pytest.raises(ValueError, match="가중 기하평균"):
        options.save({
            "detectors": {
                name: {"includedInTotal": True}
                for name in options.DETECTOR_SCHEMA
            },
            "ensemble": {
                "method": "weightedGeometric",
                "weights": {"sonics": 0, "lofcz": 0, "artifactnet": 0, "attribution": 5},
            },
        })

    assert not target.exists()


def test_defaults_include_all_three_installed_detectors() -> None:
    defaults = options.default_options()

    assert defaults["sonics"]["includedInTotal"] is True
    assert defaults["lofcz"]["includedInTotal"] is True
    assert defaults["artifactnet"]["includedInTotal"] is True


def test_defaults_match_the_locked_model_specs() -> None:
    defaults = options.default_options()

    assert defaults["sonics"]["maxWindows"] == 24
    assert defaults["sonics"]["hopSeconds"] == 2.5
    assert defaults["sonics"]["aggregation"] == "median"
    assert defaults["sonics"]["topK"] == 3
    assert defaults["lofcz"]["maxDurationS"] == 300
    assert defaults["lofcz"]["analysisPosition"] == "start"
    assert defaults["lofcz"]["aggregation"] == "mean"
    assert defaults["artifactnet"]["segmentCount"] == 11
    assert defaults["artifactnet"]["segmentSelection"] == "even"
    assert defaults["artifactnet"]["aggregation"] == "top3"
    assert defaults["artifactnet"]["minValidSegments"] == 4
    assert defaults["artifactnet"]["levelNormalize"] is False


def test_unknown_keys_and_values_fall_back_to_defaults() -> None:
    result = options.normalize({
        "detectors": {
            "sonics": {"maxWindows": 13, "aggregation": "topk", "topK": 99, "unknown": 1},
            "nope": {"maxWindows": 8},
        },
        "ensemble": {"method": "harmonic", "weights": {"sonics": "x", "lofcz": 99}},
    })

    assert result["detectors"]["sonics"]["maxWindows"] == 24
    assert result["detectors"]["sonics"]["topK"] == 3
    assert "unknown" not in result["detectors"]["sonics"]
    assert "nope" not in result["detectors"]
    assert result["ensemble"]["method"] == "robustMean"
    assert result["ensemble"]["weights"] == {"lofcz": 10.0}


def test_threshold_is_clamped_to_the_allowed_range() -> None:
    high = options.normalize({"detectors": {"sonics": {"threshold": 5}}})
    low = options.normalize({"detectors": {"sonics": {"threshold": -1}}})

    assert high["detectors"]["sonics"]["threshold"] == options.MAX_THRESHOLD
    assert low["detectors"]["sonics"]["threshold"] == options.MIN_THRESHOLD


def test_partial_payload_keeps_the_other_defaults() -> None:
    result = options.normalize({"detectors": {"artifactnet": {"includedInTotal": True}}})

    assert result["detectors"]["artifactnet"]["includedInTotal"] is True
    assert result["detectors"]["artifactnet"]["segmentCount"] == 11
    assert result["detectors"]["sonics"]["includedInTotal"] is True


def test_explicit_null_does_not_switch_off_the_total_toggle() -> None:
    # Pydantic model_dump() emits every declared field, so an omitted
    # includedInTotal arrives as None instead of a missing key.
    result = options.normalize({
        "detectors": {
            "sonics": {"includedInTotal": None, "topK": 1},
            "lofcz": {"includedInTotal": None, "maxDurationS": 60},
        },
    })

    assert result["detectors"]["sonics"]["includedInTotal"] is True
    assert result["detectors"]["sonics"]["topK"] == 1
    assert result["detectors"]["lofcz"]["includedInTotal"] is True
    assert result["detectors"]["lofcz"]["maxDurationS"] == 60
    assert result["detectors"]["lofcz"]["threshold"] == 0.5


def test_api_request_dump_round_trips_through_normalize() -> None:
    from probe.app import DetectorOptionsRequest

    payload = DetectorOptionsRequest(detectors={"sonics": {"topK": 1}}).model_dump()
    result = options.normalize(payload)

    assert result["detectors"]["sonics"]["topK"] == 1
    assert result["detectors"]["sonics"]["includedInTotal"] is True
    assert result["detectors"]["lofcz"]["includedInTotal"] is True


def test_api_request_keeps_artifactnet_level_normalize() -> None:
    from probe.app import DetectorOptionsRequest

    payload = DetectorOptionsRequest(
        detectors={"artifactnet": {"levelNormalize": True}},
    ).model_dump(exclude_unset=True)

    assert payload["detectors"]["artifactnet"]["levelNormalize"] is True


def test_describe_exposes_locked_values_and_choice_labels() -> None:
    described = options.describe()
    artifactnet = next(item for item in described["detectors"] if item["name"] == "artifactnet")
    aggregation = next(item for item in artifactnet["options"] if item["key"] == "aggregation")

    assert any(item["value"] == "44,100 Hz" for item in artifactnet["locked"])
    assert artifactnet["lockedNote"]
    assert aggregation["choices"][0] == {"value": "median", "label": "중앙값 (공식)"}
    assert aggregation["default"] == "top3"
    assert aggregation["choices"][2] == {"value": "top3", "label": "상위 3개 평균 (기본)"}
    assert {method["value"] for method in described["ensemble"]["methods"]} == {
        "geometric", "arithmetic", "median", "weightedGeometric", "robustMean",
    }


def test_save_round_trips_through_the_options_file(tmp_path, monkeypatch) -> None:
    target = tmp_path / "detector-options.json"
    monkeypatch.setattr(options, "OPTIONS_PATH", target)

    saved = options.save({"detectors": {"sonics": {"topK": 1, "includedInTotal": False}}})
    options._invalidate()

    assert target.is_file()
    assert saved["detectors"]["sonics"]["topK"] == 1
    assert options.for_detector("sonics")["topK"] == 1
    assert options.included_in_total("sonics") is False
    assert options.included_in_total("lofcz") is True


def test_current_reloads_when_the_file_changes(tmp_path, monkeypatch) -> None:
    target = tmp_path / "detector-options.json"
    monkeypatch.setattr(options, "OPTIONS_PATH", target)
    options._invalidate()

    assert options.for_detector("lofcz")["maxDurationS"] == 300
    options.save({"detectors": {"lofcz": {"maxDurationS": 60}}})
    assert options.for_detector("lofcz")["maxDurationS"] == 60


def test_corrupt_file_falls_back_to_defaults(tmp_path, monkeypatch) -> None:
    target = tmp_path / "detector-options.json"
    target.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(options, "OPTIONS_PATH", target)
    options._invalidate()

    assert options.load() == options.normalize(None)


@pytest.mark.parametrize("method", ["geometric", "arithmetic", "median", "weightedGeometric", "robustMean"])
def test_every_advertised_method_is_accepted(method: str) -> None:
    assert options.normalize({"ensemble": {"method": method}})["ensemble"]["method"] == method


def test_partial_merge_preserves_unrelated_saved_detector_values() -> None:
    current = options.normalize({
        "detectors": {
            "artifactnet": {"includedInTotal": True, "segmentCount": 11},
            "lofcz": {"maxDurationS": 60},
        },
        "ensemble": {"method": "median", "weights": {"sonics": 2}},
    })

    merged = options.merge(current, {"detectors": {"sonics": {"topK": 1}}})

    assert merged["detectors"]["sonics"]["topK"] == 1
    assert merged["detectors"]["artifactnet"]["includedInTotal"] is True
    assert merged["detectors"]["artifactnet"]["segmentCount"] == 11
    assert merged["detectors"]["lofcz"]["maxDurationS"] == 60
    assert merged["ensemble"] == current["ensemble"]


def test_save_rejects_all_zero_weights_for_included_detectors(tmp_path, monkeypatch) -> None:
    target = tmp_path / "detector-options.json"
    monkeypatch.setattr(options, "OPTIONS_PATH", target)

    with pytest.raises(ValueError, match="하나 이상의 가중치"):
        options.save({
            "detectors": {
                name: {"includedInTotal": name != "attribution"}
                for name in options.DETECTOR_SCHEMA
            },
            "ensemble": {
                "method": "weightedGeometric",
                "weights": {"sonics": 0, "lofcz": 0, "artifactnet": 0, "attribution": 0},
            },
        })

    assert not target.exists()


def test_all_zero_guard_ignores_unimplemented_attribution_default(tmp_path, monkeypatch) -> None:
    target = tmp_path / "detector-options.json"
    monkeypatch.setattr(options, "OPTIONS_PATH", target)

    with pytest.raises(ValueError, match="하나 이상의 가중치"):
        options.save({
            "detectors": {
                name: {"includedInTotal": True}
                for name in ("sonics", "lofcz", "artifactnet")
            },
            "ensemble": {
                "method": "weightedGeometric",
                "weights": {"sonics": 0, "lofcz": 0, "artifactnet": 0},
            },
        })


def test_invalid_partial_patch_keeps_saved_values() -> None:
    current = options.normalize({
        "detectors": {"sonics": {"aggregation": "topk", "topK": 5}},
        "ensemble": {"method": "median", "weights": {"sonics": 2}},
    })

    merged = options.merge(current, {
        "detectors": {"sonics": {"aggregation": "invalid", "topK": "invalid"}},
        "ensemble": {"method": "invalid", "weights": {"sonics": "invalid"}},
    })

    assert merged["detectors"]["sonics"]["aggregation"] == "topk"
    assert merged["detectors"]["sonics"]["topK"] == 5
    assert merged["ensemble"] == current["ensemble"]
