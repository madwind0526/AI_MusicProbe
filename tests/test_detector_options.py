import pytest

from probe import detector_options as options


def test_defaults_evaluate_artifactnet_but_score_the_other_two() -> None:
    defaults = options.default_options()

    assert defaults["sonics"]["includedInTotal"] is True
    assert defaults["lofcz"]["includedInTotal"] is True
    assert defaults["artifactnet"]["includedInTotal"] is False


def test_defaults_match_the_locked_model_specs() -> None:
    defaults = options.default_options()

    assert defaults["sonics"]["maxWindows"] == 24
    assert defaults["sonics"]["hopSeconds"] == 2.5
    assert defaults["sonics"]["aggregation"] == "topk"
    assert defaults["sonics"]["topK"] == 3
    assert defaults["lofcz"]["maxDurationS"] == 300
    assert defaults["lofcz"]["analysisPosition"] == "start"
    assert defaults["artifactnet"]["segmentCount"] == 7
    assert defaults["artifactnet"]["segmentSelection"] == "even"
    assert defaults["artifactnet"]["aggregation"] == "median"
    assert defaults["artifactnet"]["minValidSegments"] == 4


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
    assert result["ensemble"]["method"] == "geometric"
    assert result["ensemble"]["weights"] == {"lofcz": 10.0}


def test_threshold_is_clamped_to_the_allowed_range() -> None:
    high = options.normalize({"detectors": {"sonics": {"threshold": 5}}})
    low = options.normalize({"detectors": {"sonics": {"threshold": -1}}})

    assert high["detectors"]["sonics"]["threshold"] == options.MAX_THRESHOLD
    assert low["detectors"]["sonics"]["threshold"] == options.MIN_THRESHOLD


def test_partial_payload_keeps_the_other_defaults() -> None:
    result = options.normalize({"detectors": {"artifactnet": {"includedInTotal": True}}})

    assert result["detectors"]["artifactnet"]["includedInTotal"] is True
    assert result["detectors"]["artifactnet"]["segmentCount"] == 7
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


def test_describe_exposes_locked_values_and_choice_labels() -> None:
    described = options.describe()
    artifactnet = next(item for item in described["detectors"] if item["name"] == "artifactnet")
    aggregation = next(item for item in artifactnet["options"] if item["key"] == "aggregation")

    assert any(item["value"] == "44,100 Hz" for item in artifactnet["locked"])
    assert artifactnet["lockedNote"]
    assert aggregation["choices"][0] == {"value": "median", "label": "중앙값 (공식)"}
    assert {method["value"] for method in described["ensemble"]["methods"]} == {
        "geometric", "arithmetic", "median", "weightedGeometric",
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


@pytest.mark.parametrize("method", ["geometric", "arithmetic", "median", "weightedGeometric"])
def test_every_advertised_method_is_accepted(method: str) -> None:
    assert options.normalize({"ensemble": {"method": method}})["ensemble"]["method"] == method
