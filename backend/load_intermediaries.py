"""
load_intermediaries.py
----------------------
Seeds the three billing intermediary platforms into the intermediaries table.
Run once after 11_intermediaries.sql has been executed.

Usage:
    cd /Users/deanpedersen/Projects/solrei/CPT_App
    python3 backend/load_intermediaries.py
"""

from backend.database import get_db
import sys
import os

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


PLATFORMS = [
    {
        "name":            "Headway",
        "display_name":    "Headway",
        "website":         "https://headway.co",
        "fee_description": "0% fee — rates pre-negotiated with payers directly",
        "notes":           (
            "Headway negotiates directly with insurance companies and pays providers "
            "a flat per-session rate. Rates vary by payer, CPT code, and state. "
            "Providers receive payment within a few days of session completion."
        ),
    },
    {
        "name":            "Alma",
        "display_name":    "Alma",
        "website":         "https://helloalma.com",
        "fee_description": "0% fee — rates pre-negotiated with payers directly",
        "notes":           (
            "Alma negotiates rates with payers and pays providers directly. "
            "Similar model to Headway. Rates are set at the platform level per payer."
        ),
    },
    {
        "name":            "Grow Therapy",
        "display_name":    "Grow Therapy",
        "website":         "https://growtherapy.com",
        "fee_description": "0% fee — rates pre-negotiated with payers directly",
        "notes":           (
            "Grow Therapy handles insurance credentialing and billing for providers. "
            "Pays providers a negotiated rate per session, per payer."
        ),
    },
]


def seed_intermediaries():
    inserted = 0
    skipped = 0

    with get_db() as cur:
        for p in PLATFORMS:
            cur.execute(
                """
                INSERT INTO intermediaries
                    (name, display_name, website, fee_description, notes, active)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (name) DO UPDATE SET
                    display_name    = EXCLUDED.display_name,
                    website         = EXCLUDED.website,
                    fee_description = EXCLUDED.fee_description,
                    notes           = EXCLUDED.notes,
                    active          = TRUE
                RETURNING intermediary_id, name
                """,
                (
                    p["name"],
                    p["display_name"],
                    p["website"],
                    p["fee_description"],
                    p["notes"],
                ),
            )
            row = cur.fetchone()
            print(f"  ✓  {row['name']}  (id={row['intermediary_id']})")
            inserted += 1

    print(f"\nDone — {inserted} intermediary platform(s) seeded.")
    print("\nNext step: download the rate template from the dashboard,")
    print("fill in your Headway/Alma/Grow Therapy rates, and upload the CSV.\n")


if __name__ == "__main__":
    print("Seeding intermediary platforms...")
    seed_intermediaries()
