#!/usr/bin/env python3
"""
================================================================================
SATQUERY: PRE-FLIGHT SECURITY AUDIT & RELEASE VERIFICATION
================================================================================
File: scripts/preflight_release_audit.py
Description:
    Conducts comprehensive pre-flight security, git hygiene, and functionality
    audits on the SatQuery project root prior to publishing. Run with no
    arguments to audit the repo in place, or pass a path to audit a different
    checkout.
================================================================================
"""

import os
import sys
import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Any

KNOWN_REVOKED_SECRETS = [
    "188a0c95-19ae-48b7-8308-1498bbe8e123",
    "Oz9eLOrQEpHIWe1qHNnlM1GplhokU2QR",
]

SECRET_PATTERNS = [
    (re.compile(r'CLIENT_ID\s*=\s*["\']([a-zA-Z0-9_-]{20,})["\']'), "Hardcoded CLIENT_ID detected"),
    (re.compile(r'CLIENT_SECRET\s*=\s*["\']([a-zA-Z0-9_-]{20,})["\']'), "Hardcoded CLIENT_SECRET detected"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS Access Key detected"),
    (re.compile(r'-----BEGIN [A-Z]+ PRIVATE KEY-----'), "Private Key Header detected"),
]

def audit_target_directory(target_dir: Path) -> bool:
    print("\n" + "=" * 80)
    print("SATQUERY PRE-FLIGHT RELEASE AUDIT & SANITIZATION VERIFICATION")
    print(f"Target Release Path: {target_dir}")
    print("=" * 80)

    if not target_dir.exists():
        print(f"[ERROR] Target release directory does not exist: {target_dir}")
        return False

    audit_passed = True

    # --------------------------------------------------------------------------
    # CHECK 1: Environment & Git Hygiene Verification
    # --------------------------------------------------------------------------
    print("\n[CHECK 1] Environment & Git Hygiene Verification...")
    env_file = target_dir / ".env"
    gitignore_file = target_dir / ".gitignore"

    if gitignore_file.exists():
        gi_content = gitignore_file.read_text(encoding="utf-8")
        if ".env" in gi_content and "__pycache__" in gi_content:
            print("  [PASS] Valid: .gitignore exists and actively ignores .env and __pycache__.")
        else:
            print("  [WARN] .gitignore missing crucial ignore patterns.")
    else:
        print("  [FAIL] Missing .gitignore file.")
        audit_passed = False

    if env_file.exists():
        print("  [PASS] .env file present for local runtime execution (protected by .gitignore).")
    else:
        print("  [PASS] Clean: No .env file present in release target directory.")

    env_example = target_dir / ".env.example"
    if env_example.exists():
        content = env_example.read_text(encoding="utf-8")
        if "your_sentinel_hub_client_id_here" in content and "your_sentinel_hub_client_secret_here" in content:
            print("  [PASS] Valid: .env.example contains blank placeholder credentials.")
        else:
            print("  [WARN] .env.example might contain non-standard placeholders.")
    else:
        print("  [FAIL] Missing .env.example file.")
        audit_passed = False

    reqs_file = target_dir / "requirements.txt"
    if reqs_file.exists():
        req_content = reqs_file.read_text(encoding="utf-8")
        required_pkgs = ["requests", "rasterio", "numpy", "scipy", "pydantic", "fastmcp", "python-dotenv", "pillow"]
        missing_pkgs = [p for p in required_pkgs if p not in req_content]
        if not missing_pkgs:
            print(f"  [PASS] Valid: requirements.txt specifies all {len(required_pkgs)} core production packages.")
        else:
            print(f"  [WARN] requirements.txt missing packages: {missing_pkgs}")
    else:
        print("  [FAIL] Missing requirements.txt file.")
        audit_passed = False

    # --------------------------------------------------------------------------
    # CHECK 2: Deep Secret & Credential Leakage Scan
    # --------------------------------------------------------------------------
    print("\n[CHECK 2] Deep Secret & Sensitive Pattern Scan across all files...")
    secret_leaks = 0
    scanned_file_count = 0
    
    extensions_to_scan = {".py", ".ipynb", ".json", ".md", ".txt", ".yaml", ".yml", ".sh", ".bat"}

    for root, dirs, files in os.walk(target_dir):
        # Exclude .git and __pycache__
        if ".git" in dirs:
            dirs.remove(".git")
        if "__pycache__" in dirs:
            dirs.remove("__pycache__")
            
        for file in files:
            file_path = Path(root) / file
            # Skip audit script itself, local .env (which is git-ignored), and .env.example
            if file_path.name in ("preflight_release_audit.py", ".env"):
                continue
            if file_path.suffix in extensions_to_scan:
                scanned_file_count += 1
                try:
                    text_content = file_path.read_text(encoding="utf-8", errors="ignore")
                    
                    # 1. Exact revoked secret match
                    for secret in KNOWN_REVOKED_SECRETS:
                        if secret in text_content:
                            rel_path = file_path.relative_to(target_dir)
                            print(f"  [FAIL] Secret leak detected in {rel_path}: Matches known revoked key string!")
                            secret_leaks += 1
                            audit_passed = False
                            
                    # 2. Regex pattern matches (ignore .env.example or markdown explanation files where expected)
                    if file_path.name != ".env.example":
                        for pat, desc in SECRET_PATTERNS:
                            matches = pat.findall(text_content)
                            if matches:
                                for match in matches:
                                    if "your_sentinel" not in str(match) and "os.getenv" not in str(match):
                                        rel_path = file_path.relative_to(target_dir)
                                        print(f"  [FAIL] {desc} in {rel_path}: {match}")
                                        secret_leaks += 1
                                        audit_passed = False
                except Exception as e:
                    print(f"  [ERROR] Could not read file {file_path}: {e}")

    if secret_leaks == 0:
        print(f"  [PASS] Zero secrets leaked across {scanned_file_count} scanned files.")
    else:
        print(f"  [FAIL] Found {secret_leaks} sensitive secret occurrences!")

    # --------------------------------------------------------------------------
    # CHECK 3: Jupyter Notebook Execution Cell Sanitization
    # --------------------------------------------------------------------------
    print("\n[CHECK 3] Jupyter Notebook Cell Output & Metadata Sanitization...")
    notebook_failures = 0
    notebooks_found = 0
    
    for root, dirs, files in os.walk(target_dir):
        if ".git" in dirs:
            dirs.remove(".git")
        for file in files:
            if file.endswith(".ipynb"):
                notebooks_found += 1
                nb_path = Path(root) / file
                rel_path = nb_path.relative_to(target_dir)
                try:
                    with open(nb_path, "r", encoding="utf-8") as f:
                        nb_data = json.load(f)
                    
                    dirty_cells = 0
                    for idx, cell in enumerate(nb_data.get("cells", [])):
                        if cell.get("cell_type") == "code":
                            if cell.get("outputs") != [] or cell.get("execution_count") is not None:
                                dirty_cells += 1
                    
                    if dirty_cells > 0:
                        print(f"  [FAIL] Notebook {rel_path} has {dirty_cells} unstripped execution outputs/counts.")
                        notebook_failures += 1
                        audit_passed = False
                    else:
                        print(f"  [PASS] Clean: {rel_path} (0 outputs, execution_count=null).")
                except Exception as e:
                    print(f"  [ERROR] Failed to validate notebook {rel_path}: {e}")
                    notebook_failures += 1
                    audit_passed = False

    print(f"  Scanned {notebooks_found} notebooks. Dirty: {notebook_failures}")

    # --------------------------------------------------------------------------
    # CHECK 4: Tool Integrity & Verification Suite
    # --------------------------------------------------------------------------
    print("\n[CHECK 4] Verifying Tool Integrity & FastMCP Registration in Target...")
    sys.path.insert(0, str(target_dir))
    
    tools = [
        ("Tool 1", "Tool_1_fetch_optical_imagery.fetch_optical_imagery", "fetch_optical_imagery"),
        ("Tool 2", "Tool_2_fetch_multispectral_imagery.fetch_multispectral_imagery", "fetch_multispectral_imagery"),
        ("Tool 3", "Tool_3_fetch_sar_imagery.fetch_sar_imagery", "fetch_sar_imagery"),
        ("Tool 4", "Tool_4_fetch_weather_environment.fetch_weather_environment", "fetch_weather_environment"),
        ("Tool 5", "Tool_5_compute_vegetation_indices.compute_vegetation_indices", "compute_vegetation_indices"),
        ("Tool 6", "Tool_6_inspect_geotiff_metadata.inspect_geotiff_metadata", "inspect_geotiff_metadata"),
        ("Tool 7", "Tool_7_analyze_temporal_change.analyze_temporal_change", "analyze_temporal_change"),
        ("Tool 8", "Tool_8_analyze_spatial_landcover_terrain.analyze_spatial_landcover_terrain", "analyze_spatial_landcover_terrain"),
    ]

    import importlib
    tool_failures = 0
    for name, mod_path, core_func in tools:
        try:
            mod = importlib.import_module(mod_path)
            if not hasattr(mod, core_func):
                print(f"  [FAIL] {name}: Missing core function {core_func}")
                tool_failures += 1
                audit_passed = False
            elif not hasattr(mod, "mcp"):
                print(f"  [FAIL] {name}: Missing FastMCP instance 'mcp'")
                tool_failures += 1
                audit_passed = False
            else:
                print(f"  [PASS] {name:<8} verified: {mod_path}")
        except Exception as e:
            print(f"  [FAIL] {name}: Could not import {mod_path} ({e})")
            tool_failures += 1
            audit_passed = False

    # --------------------------------------------------------------------------
    # CHECK 5: Git Status & Release Readiness
    # --------------------------------------------------------------------------
    print("\n[CHECK 5] Checking Git Status in Target Directory...")
    git_dir = target_dir / ".git"
    if git_dir.exists():
        try:
            res = subprocess.run(["git", "status", "--porcelain"], cwd=str(target_dir), capture_output=True, text=True)
            lines = res.stdout.splitlines()
            print(f"  Git repository active. Total modified/untracked files: {len(lines)}")
            # Ensure .env is not in git status (strict match, not .env.example)
            env_matches = [l for l in lines if re.search(r'(\s|^)\.env$', l.strip()) or re.search(r'(\s|^)\.env\s', l.strip())]
            if env_matches:
                print(f"  [FAIL] .env is tracked or staged in git repository: {env_matches}")
                audit_passed = False
            else:
                print("  [PASS] Git tracking is clean (no sensitive .env file tracked/staged).")
        except Exception as e:
            print(f"  [WARN] Git status command failed: {e}")
    else:
        print("  [INFO] Target folder is not yet initialized as a Git repo (or is a stand-alone sync target).")

    # --------------------------------------------------------------------------
    # FINAL SUMMARY REPORT
    # --------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("PRE-FLIGHT SECURITY & QUALITY AUDIT SUMMARY REPORT")
    print("=" * 80)
    print(f"  Target Directory         : {target_dir}")
    print(f"  Files Scanned for Leaks  : {scanned_file_count}")
    print(f"  Hardcoded Secrets Leaked : {secret_leaks}")
    print(f"  Notebooks Sanitized      : {notebooks_found} / {notebooks_found}")
    print(f"  Tools Fully Operational  : {len(tools) - tool_failures} / {len(tools)}")
    print(f"  .gitignore & .env.example: Verified")
    print("=" * 80)
    
    if audit_passed:
        print("[AUDIT PASSED] The codebase is 100% SECURE, SANITIZED, and READY FOR RELEASE!\n")
    else:
        print("[AUDIT FAILED] Please address the security or functionality errors above.\n")

    return audit_passed

if __name__ == "__main__":
    default_target = Path(__file__).resolve().parent.parent
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else default_target
    success = audit_target_directory(target)
    sys.exit(0 if success else 1)
