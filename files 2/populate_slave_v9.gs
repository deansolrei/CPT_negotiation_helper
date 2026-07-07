/**
 * Solrei SLAVE – Rate Sync from MASTER (v9 — unified output with provider column)
 *
 * Changes from v8:
 *  - All four channels (Alma / Headway / Grow Therapy / SBH) go into ONE tab: intermediary_rates
 *  - Added 'provider' column: JJ, KR, LK, or blank (COMMON — applies to all providers)
 *  - Provider prefix read from MASTER date row headers (e.g. "[JJ] Headway 7/4/26")
 *  - Payer names normalized to match dashboard canonical names exactly
 *  - direct_rates tab still written as a backup/reference (unchanged)
 *  - Single CSV download feeds entire dashboard — no separate SBH upload needed
 *
 * HOW TO USE:
 * 1. In SLAVE Google Sheet → Extensions → Apps Script
 * 2. Replace ALL code with this, Save
 * 3. Run → syncRatesFromMaster
 * 4. Grant permissions if prompted (one-time)
 *
 * DOWNLOAD AFTER RUNNING:
 *   Tab "intermediary_rates" → File > Download > CSV → upload to dashboard
 *   (direct_rates tab also written as reference — not needed for upload)
 */

var MASTER_SHEET_ID = '1okxQgWz400amUqC_i-4C8AJcFvZkjD0f2yjl87MIT-c';
var MASTER_TAB      = 'Rates';
var SLAVE_TAB       = 'intermediary_rates';
var DIRECT_TAB      = 'direct_rates';

// ── State block start rows in MASTER (1-indexed) ──────────────
var STATE_TO_ROW = {
  AK: 3,   AZ: 11,  CO: 19,  CT: 27,  DC: 35,  FL: 43,
  HI: 51,  IA: 59,  ID: 67,  MD: 83,  MN: 99,  MT: 107,
  ND: 115, NE: 123, NH: 131, NM: 139, NV: 147, OR: 155,
  SD: 163, UT: 171, WA: 187, WY: 195,
};

// ── CPT row offsets within each state block ───────────────────
var CPT_OFFSET = { '99214': 2, '99215': 3, '90833': 4, '90836': 5, '90838': 6 };

// ── Plan groups — canonical dashboard payer names ─────────────
// col = 1-indexed Alma column; sub-cols: +0=Alma, +1=Headway, +2=Grow, +3=SBH
var PLAN_GROUPS = [
  { plan: 'Aetna',                              col: 2   },
  { plan: 'Cigna',                              col: 6   },
  { plan: 'Optum/UHC/Oscar',                    col: 10  },
  { plan: 'Carelon Behavioral Health',          col: 14  },
  { plan: 'Ambetter',                           col: 18  },
  { plan: 'Ambetter',                           col: 22  }, // Ambetter Washington — same family
  { plan: 'BCBS - Florida Blue',                col: 26  },
  { plan: 'BCBS - Florida Blue',                col: 30  }, // Medicare Advantage — same payer
  { plan: 'BCBS - Arizona',                     col: 34  },
  { plan: 'BCBS - Massachusetts',               col: 38  },
  { plan: 'BCBS - Minnesota',                   col: 42  },
  { plan: 'BCBS - Minnesota',                   col: 46  }, // Medicaid
  { plan: 'BCBS - Minnesota',                   col: 50  }, // Medicaid Advantage
  { plan: 'BCBS - Anthem Colorado',             col: 54  }, // HMO
  { plan: 'BCBS - Anthem Colorado',             col: 58  }, // PPO
  { plan: 'BCBS - Anthem Connecticut',          col: 62  },
  { plan: 'BCBS - Anthem Indiana',              col: 66  },
  { plan: 'BCBS - Anthem Maine',                col: 70  },
  { plan: 'BCBS - Anthem Nevada',               col: 74  },
  { plan: 'BCBS - Anthem New Hampshire',        col: 78  },
  { plan: 'BCBS - Horizon New Jersey',          col: 82  },
  { plan: 'BCBS - Independence Pennsylvania',   col: 86  },
  { plan: 'BCBS - Premera Washington',          col: 90  },
  { plan: 'BCBS - Regence Washington',          col: 94  },
  { plan: 'BCBS - Regence Oregon',              col: 98  },
  { plan: 'BCBS - Wellmark Iowa',               col: 102 },
];

// ── All four channels ─────────────────────────────────────────
var CHANNELS = [
  { name: 'Alma',         offset: 0 },
  { name: 'Headway',      offset: 1 },
  { name: 'Grow Therapy', offset: 2 },
  { name: 'SBH',          offset: 3 },
];


// ══════════════════════════════════════════════════════════════
//  HELPER: Parse provider prefix from a header cell
//  "[JJ] Headway 7/4/26" → "JJ"
//  "Alma 03/31/26"        → "" (COMMON)
// ══════════════════════════════════════════════════════════════

function _parseProvider(cellText) {
  var text = String(cellText || '').trim();
  var match = text.match(/^\[([A-Z]{2,3})\]/);
  return match ? match[1] : '';
}


// ══════════════════════════════════════════════════════════════
//  HELPER: Parse effective date from header cell text
//  "[JJ] Headway 7/4/26" → "2026-07-04"
// ══════════════════════════════════════════════════════════════

function _parseDate(cellText) {
  var text = String(cellText || '');
  var match = text.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
  if (!match) return '';
  var yr = match[3].length === 2 ? '20' + match[3] : match[3];
  return yr + '-' + ('0' + match[1]).slice(-2) + '-' + ('0' + match[2]).slice(-2);
}


// ══════════════════════════════════════════════════════════════
//  HELPER: Parse a rate value from a cell
//  Returns numeric value or null if empty/invalid
// ══════════════════════════════════════════════════════════════

function _parseRate(val) {
  if (typeof val === 'number' && !isNaN(val) && val > 0) return val;
  if (typeof val === 'string') {
    var cleaned = val.replace(/[$,\s]/g, '');
    var num = parseFloat(cleaned);
    if (!isNaN(num) && num > 0) return num;
  }
  return null;
}


// ══════════════════════════════════════════════════════════════
//  MAIN FUNCTION
// ══════════════════════════════════════════════════════════════

function syncRatesFromMaster() {
  var masterSS    = SpreadsheetApp.openById(MASTER_SHEET_ID);
  var masterSheet = masterSS.getSheetByName(MASTER_TAB);
  // Read 210 rows × 106 cols — covers all 26 plan groups (last SBH col = 105)
  var masterData  = masterSheet.getRange(1, 1, 210, 106).getValues();

  var slaveSS = SpreadsheetApp.getActiveSpreadsheet();

  var intermediaryCount = _syncIntermediaryRates(slaveSS, masterData);
  var directCount       = _syncDirectRatesBackup(slaveSS, masterData);

  slaveSS.toast(
    intermediaryCount + ' rates synced to intermediary_rates tab\n' +
    '(includes Alma, Headway, Grow Therapy, and SBH Direct Submit)\n\n' +
    directCount + ' SBH rates also written to direct_rates tab (reference)\n\n' +
    'Download intermediary_rates tab as CSV and upload to dashboard.',
    'Sync Complete!',
    15
  );
}


// ══════════════════════════════════════════════════════════════
//  INTERMEDIARY RATES — unified tab with all 4 channels + provider
// ══════════════════════════════════════════════════════════════

function _syncIntermediaryRates(slaveSS, masterData) {
  var sheet = slaveSS.getSheetByName(SLAVE_TAB);
  if (!sheet) { sheet = slaveSS.insertSheet(SLAVE_TAB); }
  sheet.clearContents();

  // Header — 7 columns now includes provider
  sheet.getRange(1, 1, 1, 7).setValues(
    [['intermediary_name', 'payer_name', 'cpt_code', 'state', 'allowed_amount', 'effective_date', 'provider']]
  );

  var outputRows = [];
  var count      = 0;
  var states     = Object.keys(STATE_TO_ROW);
  var cptCodes   = Object.keys(CPT_OFFSET);

  for (var si = 0; si < states.length; si++) {
    var state    = states[si];
    var stateRow = STATE_TO_ROW[state];  // 1-indexed block start

    for (var pi = 0; pi < PLAN_GROUPS.length; pi++) {
      var pg = PLAN_GROUPS[pi];

      for (var ci = 0; ci < CHANNELS.length; ci++) {
        var channel = CHANNELS[ci];
        var colNum  = pg.col + channel.offset;  // 1-indexed

        // Read provider prefix and effective date from the date header row
        // Date row = stateRow (0-indexed: stateRow - 1 + 1 = stateRow)
        var headerCell = masterData[stateRow][colNum - 1];
        var provider   = _parseProvider(headerCell);  // 'JJ', 'KR', 'LK', or ''
        var effDate    = _parseDate(headerCell);

        for (var ki = 0; ki < cptCodes.length; ki++) {
          var cpt       = cptCodes[ki];
          var masterRow = stateRow + CPT_OFFSET[cpt];   // 1-indexed
          var val       = masterData[masterRow - 1][colNum - 1];  // 0-indexed
          var rate      = _parseRate(val);

          if (rate !== null) {
            outputRows.push([
              channel.name,   // intermediary_name
              pg.plan,        // payer_name (canonical dashboard name)
              cpt,            // cpt_code
              state,          // state
              rate,           // allowed_amount
              effDate,        // effective_date
              provider,       // provider: JJ / KR / LK / '' (blank = COMMON)
            ]);
            count++;
          }
        }
      }
    }
  }

  if (outputRows.length > 0) {
    sheet.getRange(2, 1, outputRows.length, 7).setValues(outputRows);
    sheet.getRange(2, 5, outputRows.length, 1).setNumberFormat('$#,##0.00');
  }

  return count;
}


// ══════════════════════════════════════════════════════════════
//  DIRECT RATES BACKUP TAB (SBH only — reference, not for upload)
// ══════════════════════════════════════════════════════════════

function _syncDirectRatesBackup(slaveSS, masterData) {
  var sheet = slaveSS.getSheetByName(DIRECT_TAB);
  if (!sheet) { sheet = slaveSS.insertSheet(DIRECT_TAB); }
  sheet.clearContents();

  sheet.getRange(1, 1, 1, 6).setValues(
    [['payer_name', 'cpt_code', 'state', 'allowed_amount', 'effective_date', 'provider']]
  );

  var outputRows = [];
  var count      = 0;
  var states     = Object.keys(STATE_TO_ROW);
  var cptCodes   = Object.keys(CPT_OFFSET);

  for (var si = 0; si < states.length; si++) {
    var state    = states[si];
    var stateRow = STATE_TO_ROW[state];

    for (var pi = 0; pi < PLAN_GROUPS.length; pi++) {
      var pg        = PLAN_GROUPS[pi];
      var sbhColNum = pg.col + 3;  // SBH = col+3

      var headerCell = masterData[stateRow][sbhColNum - 1];
      var provider   = _parseProvider(headerCell);
      var effDate    = _parseDate(headerCell);

      for (var ki = 0; ki < cptCodes.length; ki++) {
        var cpt       = cptCodes[ki];
        var masterRow = stateRow + CPT_OFFSET[cpt];
        var val       = masterData[masterRow - 1][sbhColNum - 1];
        var rate      = _parseRate(val);

        if (rate !== null) {
          outputRows.push([pg.plan, cpt, state, rate, effDate, provider]);
          count++;
        }
      }
    }
  }

  if (outputRows.length > 0) {
    sheet.getRange(2, 1, outputRows.length, 6).setValues(outputRows);
    sheet.getRange(2, 4, outputRows.length, 1).setNumberFormat('$#,##0.00');
  }

  return count;
}


// ══════════════════════════════════════════════════════════════
//  MENU
// ══════════════════════════════════════════════════════════════

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Solrei Rates')
    .addItem('Sync from MASTER', 'syncRatesFromMaster')
    .addToUi();
}
