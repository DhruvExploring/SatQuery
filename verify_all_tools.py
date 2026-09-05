#!/usr/bin/env python3
"""
================================================================================
SATQUERY: ECOSYSTEM INTEGRITY & TOOL DISCOVERY VERIFICATION
================================================================================
File: verify_all_tools.py
Description:
    Verifies that all 8 standardized tools and root engines in the SatQuery
    ecosystem load properly, export their core functions, and register FastMCP.
================================================================================
"""

import sys
import importlib
from pathlib import Path

# Add current folder to sys.path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

TOOLS_TO_CHECK = [
    ("Tool 1", "Tool_1_fetch_optical_imagery.fetch_optical_imagery", "fetch_optical_imagery"),
    ("Tool 2", "Tool_2_fetch_multispectral_imagery.fetch_multispectral_imagery", "fetch_multispectral_imagery"),
    ("Tool 3", "Tool_3_fetch_sar_imagery.fetch_sar_imagery", "fetch_sar_imagery"),
    ("Tool 4", "Tool_4_fetch_weather_environment.fetch_weather_environment", "fetch_weather_environment"),
    ("Tool 5", "Tool_5_compute_vegetation_indices.compute_vegetation_indices", "compute_vegetation_indices"),
    ("Tool 6", "Tool_6_inspect_geotiff_metadata.inspect_geotiff_metadata", "inspect_geotiff_metadata"),
    ("Tool 7", "Tool_7_analyze_temporal_change.analyze_temporal_change", "analyze_temporal_change"),
    ("Tool 8", "Tool_8_analyze_spatial_landcover_terrain.analyze_spatial_landcover_terrain", "analyze_spatial_landcover_terrain"),
]

def verify_ecosystem() -> bool:
    print("\n" + "=" * 80)
    print("SATQUERY 8-TOOL ECOSYSTEM & FASTMCP DISCOVERY VERIFICATION")
    print("=" * 80)
    
    all_pass = True
    for name, mod_path, core_func in TOOLS_TO_CHECK:
        try:
            mod = importlib.import_module(mod_path)
            assert hasattr(mod, core_func), f"{name} missing core function '{core_func}'"
            assert hasattr(mod, "mcp"), f"{name} missing FastMCP instance 'mcp'"
            print(f"  [PASS] {name:<8} | Module: {mod_path:<65} | Func: {core_func} | FastMCP: OK")
        except Exception as e:
            print(f"  [FAIL] {name:<8} | Module: {mod_path:<65} | Error: {e}")
            all_pass = False

    # Also verify Master Server and Orchestration
    for name, mod_path in [
        ("Server", "satquery_server"),
        ("Workflows", "satquery_workflows"),
        ("Phase 3 Agent", "run_phase3"),
    ]:
        try:
            mod = importlib.import_module(mod_path)
            print(f"  [PASS] {name:<8} | Module: {mod_path:<65} | Status: LOADED OK")
        except Exception as e:
            print(f"  [FAIL] {name:<8} | Module: {mod_path:<65} | Error: {e}")
            all_pass = False

    print("=" * 80)
    if all_pass:
        print("[SUCCESS] ALL 8 TOOLS & ORCHESTRATION ENGINES ARE FULLY OPERATIONAL!\n")
    else:
        print("[FAILURE] ONE OR MORE MODULES FAILED VERIFICATION.\n")
    return all_pass

if __name__ == "__main__":
    success = verify_ecosystem()
    sys.exit(0 if success else 1)
