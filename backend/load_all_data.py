"""
load_all_data.py
----------------
Master data loader. Runs all import scripts in the correct order:
  1. Medicare 2026 benchmark rates  (foundation for all comparisons)
  2. Florida Blue fee schedule      (real contracted rates, 80% of Medicare)
  3. Other payer fee schedules      (estimated rates for Wellmark, Aetna,
                                     Ambetter, Cigna, Optum/UHC)
  4. Claims volume (2025 estimates) (unlocks revenue gap dollar math)

Safe to re-run: all imports use upsert logic (INSERT ... ON CONFLICT DO UPDATE).

Run from the project root:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_all_data.py
"""

import subprocess
import sys
import os

# Resolve the project root (one level up from this file's directory)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STEPS = [
    ("load_medicare_2026",   "Medicare 2026 benchmark rates"),
    ("load_florida_blue",    "Florida Blue fee schedule"),
    ("load_other_payers",    "Wellmark / Aetna / Ambetter / Cigna / Optum rates"),
    ("load_claims_volume",   "2025 claims volume estimates"),
]


def run_step(module_name, label):
    print()
    print("━" * 65)
    print(f"  STEP: {label}")
    print("━" * 65)
    script = os.path.join(PROJECT_ROOT, "backend", f"{module_name}.py")
    result = subprocess.run(
        [sys.executable, script],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        print(f"\n  ✗ FAILED (exit code {result.returncode})")
        return False
    return True


def main():
    print()
    print("╔" + "═" * 63 + "╗")
    print("║   Solrei CPT Negotiation Helper — Full Data Load           ║")
    print("╚" + "═" * 63 + "╝")

    failed = []
    for module_name, label in STEPS:
        ok = run_step(module_name, label)
        if not ok:
            failed.append(label)

    print()
    print("━" * 65)
    if failed:
        print(f"  ✗ {len(failed)} step(s) failed:")
        for f in failed:
            print(f"     - {f}")
        print("  Check that uvicorn is running: uvicorn backend.main:app --reload")
    else:
        print("  ✓ All steps completed successfully!")
        print()
        print("  Your negotiation dashboard is now fully loaded.")
        print("  Open these in your browser:")
        print()
        print("  Payer summary (biggest opportunities first):")
        print("    http://localhost:8000/api/dashboard/summary")
        print()
        print("  Full dashboard (all codes, all payers):")
        print("    http://localhost:8000/api/dashboard?underpaid_only=true")
        print()
        print("  Florida Blue hit list (underpaid codes):")
        print("    http://localhost:8000/api/dashboard/underpaid/1")
        print()
        print("  Next step: build the front-end UI so your team can")
        print("  see this data without touching the API directly.")
    print("━" * 65)
    print()


if __name__ == "__main__":
    main()
