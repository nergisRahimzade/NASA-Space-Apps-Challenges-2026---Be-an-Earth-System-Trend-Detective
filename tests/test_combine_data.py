import calendar
import hashlib
import importlib.util
from datetime import date
from pathlib import Path

import dask.array as da
import netCDF4
import numpy as np
import pytest

from inspect_data import metadata_scalar

SPEC = importlib.util.spec_from_file_location(
    "combine_data", Path(__file__).resolve().parents[1] / "src" / "combine_data.py"
)
combiner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(combiner)

MONTHS = ["2003-01", "2003-02", "2003-03"]


def write_raw_test_file(tmp_path, month, *, units="K", scale=0.02):
    """Use tiny real NetCDF files to exercise combination, not the HDF4 reader."""
    first = date.fromisoformat(month + "-01")
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    path = tmp_path / f"sample_{month}.nc"
    raw = np.array([[0, 15000 + first.month, 65535], [16000, 17000, 7500]], dtype=np.uint16)
    qc = np.array([[0, 1, 2], [3, 64, 255]], dtype=np.uint8)
    bitmap = np.array([[0, 1, 2], [2**30, 2**31, 2**32 - 1]], dtype=np.uint32)
    fields = {
        "SHORTNAME": "MOD11C3", "VERSIONID": "61",
        "RANGEBEGINNINGDATE": first.isoformat(), "RANGEENDINGDATE": last.isoformat(),
    }
    with netCDF4.Dataset(path, "w", format="NETCDF4") as target:
        target.createDimension(combiner.YDIM, 2)
        target.createDimension(combiner.XDIM, 3)
        target.setncattr("CoreMetadata.0", "\n".join(
            f'OBJECT = {name}\n VALUE = "{value}"\nEND_OBJECT = {name}'
            for name, value in fields.items()
        ))
        target.setncattr("ArchiveMetadata.0", f"archive for {month}")
        target.setncattr("identifier_product_doi", "10.5067/MODIS/MOD11C3.061")
        lst = target.createVariable(
            "LST_Night_CMG", "u2", (combiner.YDIM, combiner.XDIM), fill_value=0,
        )
        lst.setncatts({"units": units, "valid_range": np.array([7500, 65535], dtype=np.uint16),
                      "scale_factor": scale, "add_offset": 0.0})
        lst.set_auto_maskandscale(False)
        lst[:] = raw
        for name, values in (("QC_Night", qc), ("Clear_sky_nights", bitmap)):
            variable = target.createVariable(
                name, values.dtype, (combiner.YDIM, combiner.XDIM), fill_value=False,
            )
            variable.set_auto_maskandscale(False)
            variable[:] = values
    return path, {"LST_Night_CMG": raw, "QC_Night": qc, "Clear_sky_nights": bitmap}


@pytest.fixture
def tiny_grid_validation(monkeypatch):
    def verify_tiny_sample(dataset, source):
        # Retain actual metadata parsing; replace only the fixed global-grid check.
        core = dataset.attrs["CoreMetadata.0"]
        assert metadata_scalar(core, "SHORTNAME") == "MOD11C3"
        assert metadata_scalar(core, "VERSIONID") == "61"
        assert dict(dataset.sizes) == {combiner.YDIM: 2, combiner.XDIM: 3}
        return (metadata_scalar(core, "RANGEBEGINNINGDATE"),
                metadata_scalar(core, "RANGEENDINGDATE"))

    monkeypatch.setattr(combiner, "verify_sample", verify_tiny_sample)


def test_calendar_accepts_real_month_lengths_including_leap_february():
    combiner.check_calendar(
        np.array(["2004-01-01", "2004-02-01", "2004-03-01"], dtype="datetime64[ns]"),
        ["2004-01", "2004-02", "2004-03"],
    )


@pytest.mark.parametrize("months", [
    ["2003-01", "2003-03"],
    ["2003-01", "2003-02", "2003-02"],
    ["2003-01", "2003-02", "2003-04"],
])
def test_calendar_rejects_missing_duplicate_or_unexpected_months(months):
    with pytest.raises(ValueError):
        combiner.check_calendar(np.array(months, dtype="datetime64[M]"), MONTHS)


def test_combination_orders_months_and_retains_lazy_raw_values(tmp_path, tiny_grid_validation):
    samples = [write_raw_test_file(tmp_path, month) for month in MONTHS]
    paths = [sample[0] for sample in samples]
    original_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    with combiner.open_combined(paths[::-1], MONTHS) as combined:
        assert combined.time.values.astype("datetime64[M]").astype(str).tolist() == MONTHS
        assert dict(combined.sizes) == {"time": 3, combiner.YDIM: 2, combiner.XDIM: 3}
        for name in samples[0][1]:
            variable = combined[name]
            assert isinstance(variable.data, da.Array)
            assert variable.dims == ("time", combiner.YDIM, combiner.XDIM)
            assert variable.dtype == samples[0][1][name].dtype
            np.testing.assert_array_equal(variable.values, np.stack([sample[1][name] for sample in samples]))
        assert combined["LST_Night_CMG"].attrs["_FillValue"] == 0
        assert combined["LST_Night_CMG"].attrs["scale_factor"] == 0.02
        assert combined["LST_Night_CMG"].attrs["units"] == "K"
        assert "CoreMetadata.0" not in combined.attrs
        assert "ArchiveMetadata.0" not in combined.attrs
        assert combined.attrs["time_coverage_start"] == "2003-01-01"
        assert combined.attrs["time_coverage_end"] == "2003-03-31"

    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths} == original_hashes


@pytest.mark.parametrize("changed", [{"units": "degC"}, {"scale": 0.01}])
def test_inconsistent_units_or_packing_are_rejected(tmp_path, tiny_grid_validation, changed):
    paths = [write_raw_test_file(tmp_path, "2003-01")[0],
             write_raw_test_file(tmp_path, "2003-02", **changed)[0]]

    with pytest.raises(ValueError, match="metadata"):
        combiner.open_combined(paths, MONTHS[:2])
