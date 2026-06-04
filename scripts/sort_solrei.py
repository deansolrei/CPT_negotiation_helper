#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║          SOLREI BEHAVIORAL HEALTH — DRIVE AUTO-SORT SCRIPT          ║
║                                                                      ║
║  Scans:  SOLREI BEHAVIORAL HEALTH/_INBOX  (in Google Drive)          ║
║  Sorts into the 9 organized sections under SOLREI BEHAVIORAL HEALTH  ║
║                                                                      ║
║  STEP 1: Run as-is (DRY_RUN = True)  → review the preview log       ║
║  STEP 2: Set DRY_RUN = False         → run again to actually move    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import os
import re
import shutil
import datetime
import time

# ─────────────────────────────────────────────────────────────────────
#  ⚙️  CONFIG
# ─────────────────────────────────────────────────────────────────────
DRY_RUN = True   # ← KEEP True for first run (preview only)

LOG_FILE = os.path.expanduser(
    f"~/Desktop/sort_solrei_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
)

# ─────────────────────────────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────────────────────────────
_log_lines = []

def log(msg=""):
    print(msg)
    _log_lines.append(msg)

def write_log():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines))
    print(f"\n📋  Log saved to: {LOG_FILE}")

# ─────────────────────────────────────────────────────────────────────
#  PATH DISCOVERY
# ─────────────────────────────────────────────────────────────────────

def find_gdrive_root():
    """
    Find the ACTIVE Google Drive 'My Drive' for the Solrei account.

    macOS CloudStorage contains multiple Google Drive mounts:
      GoogleDrive-Dean@solreibehavioralhealth.com/My Drive          ← ACTIVE (no date)
      GoogleDrive-Dean@solreibehavioralhealth.com (7-18-25 4:23 PM) ← OLD archived mount
      GoogleDrive-dean@senshinehealth.com (...)                     ← different account
      GoogleDrive-dptvfilm@gmail.com (...)                          ← different account

    Rules:
      1. Must contain 'solreibehavioralhealth' in the folder name
      2. Prefer paths WITHOUT a date suffix — those are the active mounts
      3. Fall back to dated paths only if no undated path exists
    """
    cloud_base = os.path.expanduser("~/Library/CloudStorage")
    if not os.path.isdir(cloud_base):
        return None

    undated = []
    dated   = []

    try:
        entries = list(os.scandir(cloud_base))
    except Exception as e:
        log(f"  ❌  Cannot scan CloudStorage: {e}")
        return None

    log(f"  ℹ️   All CloudStorage entries found:")
    for entry in sorted(entries, key=lambda e: e.name):
        log(f"       • {entry.name}")

    for entry in entries:
        if not entry.is_dir():
            continue
        name = entry.name

        # Must be a GoogleDrive folder for the Solrei account
        if not name.lower().startswith("googledrive-"):
            continue
        if "solreibehavioralhealth" not in name.lower():
            continue

        my_drive = os.path.join(entry.path, "My Drive")
        if not os.path.isdir(my_drive):
            continue

        # Dated entries contain a parenthesised date like "(7-18-25 4:23 PM)"
        if re.search(r'\(\d', name):
            dated.append((my_drive, name))
        else:
            undated.append((my_drive, name))

    # Prefer undated (active mount) over dated (archived)
    if undated:
        path, name = undated[0]
        log(f"  ✅  Using ACTIVE mount (no date): {name}")
        return path
    if dated:
        path, name = dated[0]
        log(f"  ⚠️   No undated mount found — using dated mount: {name}")
        log(f"       (This may be an archived mount. Verify in Finder.)")
        return path

    return None


def find_solrei_folder(gdrive):
    """
    Find SOLREI BEHAVIORAL HEALTH inside My Drive.
    1. Scan os.listdir first (works if folder is locally cached)
    2. If cloud-only, force onto disk with os.makedirs and wait for GDrive merge
    """
    # Step 1: scan
    try:
        for name in os.listdir(gdrive):
            if "SOLREI" in name.upper() and "BEHAVIORAL" in name.upper():
                full = os.path.join(gdrive, name)
                if os.path.isdir(full):
                    return full, "found on disk"
    except Exception as e:
        log(f"  ⚠️   Error scanning My Drive: {e}")

    # Step 2: force onto disk
    target = os.path.join(gdrive, "SOLREI BEHAVIORAL HEALTH")
    log(f"  ⚠️   SOLREI BEHAVIORAL HEALTH is cloud-only — forcing onto disk...")
    try:
        os.makedirs(target, exist_ok=True)
    except Exception as e:
        log(f"  ❌  makedirs failed: {e}")
        return None, None

    time.sleep(2)
    if os.path.isdir(target):
        return target, "forced onto disk (GDrive merging with cloud copy)"

    log(f"  ❌  Folder still not accessible after makedirs: {target}")
    return None, None


def find_or_create_inbox(solrei):
    """Find _INBOX in SOLREI, creating it if missing."""
    try:
        for name in os.listdir(solrei):
            if name.upper() == "_INBOX":
                return os.path.join(solrei, name)
    except Exception:
        pass
    inbox = os.path.join(solrei, "_INBOX")
    try:
        os.makedirs(inbox, exist_ok=True)
        return inbox
    except Exception as e:
        log(f"  ❌  Could not create _INBOX: {e}")
        return None


def find_section(solrei, prefix):
    """Find a section folder by numeric prefix (e.g. '01')."""
    try:
        for name in os.listdir(solrei):
            if name.startswith(prefix):
                full = os.path.join(solrei, name)
                if os.path.isdir(full):
                    return full
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────
#  📋  ROUTING RULES
#  ALL keywords are lowercase — matching is fully case-agnostic.
#  Rules checked IN ORDER — first match wins. Narrow rules first.
# ─────────────────────────────────────────────────────────────────────
SECTION_NAMES = {
    "01": "01 \u2014 ADMINISTRATION",
    "02": "02 \u2014 BILLING & REVENUE",
    "03": "03 \u2014 INSURANCE & CREDENTIALING",
    "04": "04 \u2014 CLINICAL OPERATIONS",
    "05": "05 \u2014 TECHNOLOGY & PLATFORMS",
    "06": "06 \u2014 AI & AUTOMATION",
    "07": "07 \u2014 MARKETING & BRANDING",
    "08": "08 \u2014 FINANCE & ACCOUNTING",
    "09": "09 \u2014 FACILITIES & LOCATIONS",
}

def build_rules(solrei):
    def sec(prefix):
        p = find_section(solrei, prefix)
        if not p:
            p = os.path.join(solrei, SECTION_NAMES[prefix])
        return p

    needs_review = os.path.join(solrei, "_Needs Review \u2014 Auto Sort")

    rules = [
        # ── 06 AI & AUTOMATION (most specific — check first) ──────────
        (["vapi", "webhook", "Timezone", "zapier", "make.com", "n8n",
          "openai", "chatgpt", "claude", "CoPilot", "code ", "settings", "tools", "Prompt", "Alex", "langchain", "flowise",
          "retell", "bland.ai", "synthflow", "llm", "gpt",
          "solrei-alex", "solrei alex", "API", "ARGS", "functions", "function", "Conversation", "Agent", "alex agent",
          "ai agent", "ai tool", "Virtual", "VOICE", "ai workflow", "automation",
          "ai_", "_ai.", "-ai-", "artificial intelligence"],
         sec("06"), "06 \u2014 AI & Automation"),

        # ── 03 INSURANCE & CREDENTIALING ──────────────────────────────
        (["aetna", "cigna", "medicaid", "united healthcare", "optima",
          "samaritan", "humana", "bcbs", "blue cross", "tricare",
          "magellan", "molina", "ambetter", "oscar health",
          "credentialing", "credenti", "paneling", "caqh", "pecos",
          "payer contract", "in-network", "out-of-network",
          "network agreement", "carrier", "eap provider",
          "collaborating agreement", "insurance panel",
          "provider agreement", "group npi", "taxonomy"],
         sec("03"), "03 \u2014 Insurance & Credentialing"),

        # ── 04 CLINICAL OPERATIONS ────────────────────────────────────
        (["intake form", "intake", "hipaa", "consent form", "patient form",
          "epcs", "ecps", "dea number", "lab result", "lab info", "labs",
          "clinical", "treatment plan", "progress note", "session note",
          "assessment", "diagnosis", "icd", "cpt code", "telehealth",
          "therapy note", "psychiatric", "medication", "prescription",
          "provider info", "provider bio", "clinical policy",
          "controlled substance", "prior authorization", "prior auth",
          "clinical form", "patient document", "release of information"],
         sec("04"), "04 \u2014 Clinical Operations"),

        # ── 02 BILLING & REVENUE ──────────────────────────────────────
        (["billing", "superbill", "eob", "era ", "remittance",
          "insurance claim", "collections", "copay", "deductible",
          "cash pay", "self pay", "fee schedule", "invoice",
          "revenue cycle", "insurance payment", "patient balance",
          "write-off", "charge entry", "denial", "appeal",
          "accounts receivable", "a/r", "claim submission",
          "clearinghouse", "cms-1500"],
         sec("02"), "02 \u2014 Billing & Revenue"),

        # ── 08 FINANCE & ACCOUNTING ───────────────────────────────────
        (["tax", "taxes", "irs", "w-2", "w2", "1099", "ein",
          "payroll", "quickbooks", "profit", "p&l",
          "balance sheet", "financial statement", "budget",
          "expense report", "bank statement", "accounting",
          "bookkeeping", "year-end", "quarterly report",
          "reimbursement", "accounts payable", "general ledger",
          "revenue report", "income statement", "fiscal",
          "docusign", "receipt"],
         sec("08"), "08 \u2014 Finance & Accounting"),

        # ── 07 MARKETING & BRANDING ───────────────────────────────────
        (["logo", "headshot", "brand", "WIX", "flyer", "brochure",
          "social media", "instagram", "facebook", "linkedin", "twitter",
          "seo", "google business", "yelp", "psychology today",
          "online listing", "advertisement", "marketing",
          "campaign", "email blast", "newsletter", "web copy",
          "blog post", "networking", "therapist bio",
          "profile description", "color palette", "canva",
          "graphic", "design file", "promo", "press release",
          "media kit", "photo shoot"],
         sec("07"), "07 \u2014 Marketing & Branding"),

        # ── 05 TECHNOLOGY & PLATFORMS ─────────────────────────────────
        (["tebra", "kareo", "spruce", "ehr", "emr",
          "practice management", "doxy", "zoom", "simple practice",
          "therapy notes", "blueprint", "luminare", "availity",
          "office ally", "MikroTik", "software license", "tech setup",
          "system setup", "portal setup", "TP-Link", "Archer", "login info",
          "two-factor", "2fa", "api key", "integration",
          "it setup", "it support", "domain", "email setup",
          "google workspace", "microsoft 365", "platform guide"],
         sec("05"), "05 \u2014 Technology & Platforms"),

        # ── 09 FACILITIES & LOCATIONS ─────────────────────────────────
        (["regus", "office space", "coworking", "co-working",
          "facility", "suite", "floor plan", "parking",
          "landlord", "property management", "office location",
          "virtual office", "office lease", "rent agreement",
          "building access", "key fob", "office setup"],
         sec("09"), "09 \u2014 Facilities & Locations"),

        # ── 01 ADMINISTRATION (broad — intentionally last) ────────────
        (["staff", "personnel", "employee", "human resources",
          "onboarding", "offboarding", "job description", "offer letter",
          "handbook", "policy", "procedure", "compliance",
          "legal", "contract", "agreement", "mou", "nda", "bylaws",
          "state license", "business license", "dba",
          "incorporation", "articles of", "operating agreement",
          "org chart", "team directory", "phone list",
          "office address", "solrei locations",
          "npi number", "taxonomy code", "provider number",
          "caqh profile", "license renewal", "professional license"],
         sec("01"), "01 \u2014 Administration"),
    ]

    return rules, needs_review


# ─────────────────────────────────────────────────────────────────────
#  🚫  SKIP THESE (system / temp files)
# ─────────────────────────────────────────────────────────────────────
SKIP_EXACT  = {".ds_store", ".localized", "thumbs.db", "desktop.ini"}
SKIP_PREFIX = ("~$",)

# ─────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────
def find_match(name_lower, rules):
    for keywords, dest_path, label in rules:
        for kw in keywords:
            if kw.lower() in name_lower:
                return dest_path, label, kw
    return None

def safe_dest(dest_dir, item_name):
    dest = os.path.join(dest_dir, item_name)
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(item_name)
    for i in range(1, 200):
        candidate = os.path.join(dest_dir, f"{base}_copy{i}{ext}")
        if not os.path.exists(candidate):
            return candidate
    return dest

def do_move(src, dest_dir, solrei, reason, matched_kw=None):
    item_name  = os.path.basename(src)
    dest       = safe_dest(dest_dir, item_name)
    short_dest = dest.replace(solrei, "[Solrei]")

    if DRY_RUN:
        log(f"  📦  {item_name}")
        log(f"       → {short_dest}")
        log(f"       ✏️  {reason}")
        if matched_kw:
            log(f"       🔑  matched keyword: \"{matched_kw}\"")
    else:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(src, dest)
        log(f"  ✅  MOVED: {item_name}")
        log(f"       → {short_dest}")
        log(f"       ✏️  {reason}")
        if matched_kw:
            log(f"       🔑  matched keyword: \"{matched_kw}\"")
    log()

# ─────────────────────────────────────────────────────────────────────
#  CORE SORT LOGIC
# ─────────────────────────────────────────────────────────────────────
def sort_item(item_path, rules, needs_review, solrei):
    name       = os.path.basename(item_path)
    name_lower = name.lower()

    if name_lower in SKIP_EXACT:
        log(f"  ⏭   SKIP (system file): {name}\n")
        return
    if any(name.startswith(p) for p in SKIP_PREFIX):
        log(f"  ⏭   SKIP (temp/lock file): {name}\n")
        return

    result = find_match(name_lower, rules)
    if result:
        dest_path, label, matched_kw = result
        do_move(item_path, dest_path, solrei,
                f"Pattern match: {label}", matched_kw)
    else:
        log(f"  ❓  NO MATCH: {name}")
        log(f"       Lowercased name: \"{name_lower}\"")
        log(f"       → Sending to _Needs Review for manual filing")
        log()
        do_move(item_path, needs_review, solrei,
                "No pattern match — please file manually")

# ─────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────
def main():
    mode = "DRY RUN — PREVIEW ONLY (nothing will be moved)" if DRY_RUN \
           else "\U0001f680 LIVE — FILES WILL BE MOVED"

    log("╔══════════════════════════════════════════════════════════╗")
    log("║      Solrei Behavioral Health — Drive Auto-Sort          ║")
    log("╚══════════════════════════════════════════════════════════╝")
    log(f"  Mode   : {mode}")
    log(f"  Run at : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log()
    log("🔍  Discovering paths...")

    # 1. Find the active Google Drive My Drive for the Solrei account
    gdrive = find_gdrive_root()
    if not gdrive:
        log("  ❌  Could not find an active Google Drive mount for solreibehavioralhealth.com")
        log("      Make sure Google Drive Desktop is running and signed in.")
        write_log()
        return
    log(f"  ✅  My Drive path: {gdrive}")

    # 2. Find SOLREI BEHAVIORAL HEALTH
    solrei, how = find_solrei_folder(gdrive)
    if not solrei:
        log("  ❌  Could not find or access SOLREI BEHAVIORAL HEALTH.")
        log(f"      Scanned: {gdrive}")
        log("      Folders visible on disk:")
        try:
            for name in sorted(os.listdir(gdrive)):
                log(f"        • {name}")
        except Exception as e:
            log(f"        (error: {e})")
        write_log()
        return
    log(f"  ✅  SOLREI BEHAVIORAL HEALTH ({how})")

    # 3. Find or create _INBOX
    source = find_or_create_inbox(solrei)
    if not source:
        log("  ❌  Could not find or create _INBOX.")
        write_log()
        return
    log(f"  ✅  _INBOX ready")

    # 4. List _INBOX contents
    try:
        all_items = [e.name for e in os.scandir(source)
                     if e.name.lower() not in SKIP_EXACT
                     and not any(e.name.startswith(p) for p in SKIP_PREFIX)]
    except Exception as e:
        log(f"  ❌  Cannot read _INBOX: {e}")
        write_log()
        return

    log(f"  ✅  {len(all_items)} item(s) in _INBOX:")
    for name in sorted(all_items):
        log(f"       • {name}  (lowercased: \"{name.lower()}\")")
    log()

    if not all_items:
        log("  ℹ️   _INBOX is empty — drop files or folders into it and re-run.")
        log()
        write_log()
        return

    # 5. Build rules and sort
    rules, needs_review = build_rules(solrei)

    log(f"{'─' * 58}")
    log(f"  Processing {len(all_items)} item(s)...")
    log(f"{'─' * 58}\n")

    for item_name in sorted(all_items):
        item_path = os.path.join(source, item_name)
        sort_item(item_path, rules, needs_review, solrei)

    log(f"{'═' * 58}")
    if DRY_RUN:
        log()
        log("  ✅  DRY RUN COMPLETE — nothing was moved.")
        log()
        log("  Next steps:")
        log("  1. Review every entry above carefully")
        log("  2. For ❓ NO MATCH items, add a keyword to RULES and re-run")
        log("  3. When satisfied, set DRY_RUN = False and run again")
    else:
        log()
        log("  ✅  SORT COMPLETE — items have been moved.")
        log()
        log("  Next steps:")
        log("  1. Check _Needs Review for unmatched items")
        log("  2. Verify a few sections in Google Drive look correct")
        log("  3. _INBOX is clear and ready for the next batch")
    log(f"{'═' * 58}")
    log()

    write_log()


if __name__ == "__main__":
    main()
