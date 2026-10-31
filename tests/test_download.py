import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "download", Path(__file__).resolve().parents[1] / "src" / "download.py"
)
downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(downloader)
CONTENT = downloader.HDF4_MAGIC + b"synthetic transport test"


class Granule(dict):
    def __init__(self, month, day):
        super().__init__(umm={"TemporalExtent": {"RangeDateTime": {
            "BeginningDateTime": f"2003-{month:02d}-01T00:00:00Z"
        }}})
        self.name = f"MOD11C3.A2003{day:03d}.061.2020149221031.hdf"
        self["umm"]["DataGranule"] = {"ArchiveAndDistributionInformation": [
            {"Name": self.name, "SizeInBytes": len(CONTENT)}
        ]}

    def data_links(self, access):
        assert access == "external"
        return [f"https://example.test/{self.name}"]


@pytest.fixture
def setup_download(monkeypatch):
    granules = [Granule(1, 1), Granule(2, 32), Granule(3, 60)]
    calls = {"login": [], "downloads": []}

    def search(**kwargs):
        calls["search"] = kwargs
        return granules

    def login(**kwargs):
        calls["login"].append(kwargs)
        return SimpleNamespace(authenticated=True)

    def download(selected, local_path, **kwargs):
        calls["downloads"].append((selected, kwargs))
        paths = []
        for granule in selected:
            path = local_path / granule.name
            path.write_bytes(CONTENT)
            paths.append(path)
        return paths

    monkeypatch.setattr(downloader.earthaccess, "search_data", search)
    monkeypatch.setattr(downloader.earthaccess, "login", login)
    monkeypatch.setattr(downloader.earthaccess, "download", download)
    return granules, calls, download


def test_three_file_batch_uses_chosen_product_and_phoenix_window(tmp_path, setup_download):
    _, calls, _ = setup_download
    result = downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path)
    assert calls["search"] == {
        "short_name": "MOD11C3", "version": "061", "provider": "LPCLOUD",
        "temporal": ("2003-01-01", "2003-03-31"),
        "bounding_box": (-112.4, 33.2, -111.6, 33.8),
        "sort_key": "start_date", "count": 3,
    }
    assert calls["login"] == [{"strategy": "netrc", "persist": False}]
    assert len(calls["downloads"]) == 1
    assert result["new_download_count"] == result["verified_count"] == 3
    assert result["reused_count"] == 0
    assert [item["month"] for item in result["files"]] == ["2003-01", "2003-02", "2003-03"]


def test_missing_login_never_prompts_or_downloads(tmp_path, setup_download, monkeypatch):
    _, calls, _ = setup_download

    def unavailable(**kwargs):
        calls["login"].append(kwargs)
        return SimpleNamespace(authenticated=False)

    monkeypatch.setattr(downloader.earthaccess, "login", unavailable)
    with pytest.raises(downloader.DownloadError, match="--interactive"):
        downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path)
    assert [item["strategy"] for item in calls["login"]] == ["netrc", "environment"]
    assert calls["downloads"] == []


def test_interactive_mode_logs_in_once_for_the_batch(tmp_path, setup_download):
    _, calls, _ = setup_download
    downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path, interactive=True)
    assert calls["login"] == [{"strategy": "interactive", "persist": False}]
    assert len(calls["downloads"]) == 1


def test_partial_download_is_not_reported_as_success(tmp_path, setup_download, monkeypatch):
    _, _, download = setup_download
    monkeypatch.setattr(downloader.earthaccess, "download",
                        lambda selected, **kwargs: download(selected, **kwargs)[:2])
    with pytest.raises(downloader.DownloadError, match="fewer or different"):
        downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path)


def test_invalid_existing_file_is_not_silently_reused(tmp_path, setup_download):
    granules, calls, _ = setup_download
    (tmp_path / granules[0].name).write_text("<html>Login required</html>")
    with pytest.raises(downloader.DownloadError, match="not HDF4"):
        downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path)
    assert calls["downloads"] == []


def test_reused_files_are_not_claimed_as_new_downloads(tmp_path, setup_download):
    granules, calls, _ = setup_download
    for granule in granules:
        (tmp_path / granule.name).write_bytes(CONTENT)
    result = downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path)
    assert result["new_download_count"] == 0 and result["reused_count"] == 3
    assert calls["login"] == calls["downloads"] == []


def test_duplicate_months_are_rejected(tmp_path, setup_download):
    granules, _, _ = setup_download
    granules[1] = granules[0]
    with pytest.raises(downloader.DownloadError, match="duplicate"):
        downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path)


def test_truncated_hdf_header_is_not_reused(tmp_path, setup_download):
    granules, calls, _ = setup_download
    (tmp_path / granules[0].name).write_bytes(downloader.HDF4_MAGIC + b"short")
    with pytest.raises(downloader.DownloadError, match="size differs"):
        downloader.download_samples("2003-01-01", "2003-03-31", 3, tmp_path)
    assert calls["downloads"] == []


def test_catalogue_megabytes_allow_only_metadata_rounding():
    granule = Granule(1, 1)
    granule["umm"]["DataGranule"]["ArchiveAndDistributionInformation"] = [
        {"Name": granule.name, "Size": 69.6386, "SizeUnit": "MB"}
    ]
    expected, tolerance = downloader.catalogue_size(granule, granule.name)
    assert expected == round(69.6386 * 1024**2)
    assert tolerance == 53
