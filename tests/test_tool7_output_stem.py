from pathlib import Path

from Tool_7_analyze_temporal_change.analyze_temporal_change import _safe_change_stem


def test_short_sample_stems_are_unchanged(tmp_path: Path):
    t1 = tmp_path / "sample_indices_t1.tif"
    t2 = tmp_path / "sample_indices_t2.tif"
    stem = _safe_change_stem(t1, t2, "NDVI", tmp_path)
    assert stem == "sample_indices_t1_vs_sample_indices_t2_NDVI"


def test_live_sentinel1_stems_fit_windows_filename_limit(tmp_path: Path):
    t1 = tmp_path / (
        "sentinel1_S1A_IW_GRDH_1SDV_20240710T125519_20240710T125548_"
        "054699_06A8D5_0C3A_2024-07-01_2024-07-10_sar_20260907T230559Z.tif"
    )
    t2 = tmp_path / (
        "sentinel1_S1A_IW_GRDH_1SDV_20240725T004425_20240725T004450_"
        "054910_06B02C_889D_2024-07-20_2024-07-31_sar_20260907T230606Z.tif"
    )
    stem = _safe_change_stem(t1, t2, "Band_1", tmp_path)
    name = f"{stem}_change_mask.tif"
    assert len(name) < 80
    assert len(str((tmp_path / name).resolve())) < 240
    assert stem.startswith("change_Band_1_")
