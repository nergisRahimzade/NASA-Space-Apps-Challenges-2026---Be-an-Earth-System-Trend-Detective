"""ESD-D05-BE: the contract model accepts good results and rejects bad ones clearly."""

from pathlib import Path

import pytest

from earth_system_trend.contract import ContractError, Results, load_results

FIXTURES = Path(__file__).parent / "fixtures"


def test_valid_file_loads():
    results = load_results(FIXTURES / "valid_results.json")
    assert isinstance(results, Results)
    assert results.trend.trend == "increasing"
    assert results.series[1].value is None  # missing months are allowed as null


def test_team_mock_file_loads():
    # Copy of the team's results.mock.json; if this fails, the mock and contract disagree.
    results = load_results(FIXTURES / "results_mock.json")
    assert results.units == "°C"
    assert len(results.series) == 6


def test_rejects_file_that_is_not_json():
    with pytest.raises(ContractError, match="not valid JSON"):
        load_results(FIXTURES / "broken_not_json.json")


def test_rejects_missing_required_field():
    with pytest.raises(ContractError) as excinfo:
        load_results(FIXTURES / "broken_missing_trend.json")
    message = str(excinfo.value)
    assert "trend" in message
    assert "Field required" in message


def test_rejects_wrong_types_and_out_of_range_values():
    with pytest.raises(ContractError) as excinfo:
        load_results(FIXTURES / "broken_bad_values.json")
    message = str(excinfo.value)
    assert "trend.slope" in message  # "fast" is not a number
    assert "trend.p" in message  # 1.7 is not a valid p-value
    assert "trend.trend" in message  # "up" is not an allowed direction


def test_missing_file_gives_clear_error(tmp_path):
    with pytest.raises(ContractError, match="file not found"):
        load_results(tmp_path / "nope.json")