/**
 * Solrei SLAVE – Rate Sync from MASTER (v7 — new MASTER column layout)
 *
 * Changes from v6:
 *  - MASTER_SHEET_ID updated to the new redesigned MASTER spreadsheet
 *  - STATE_TO_ROW updated: alphabetical state order, 8 rows per block
 *      (KS / ME / VT kept in MASTER but excluded from tool export)
 *  - Replaced BASE_PAYERS + STATE_EXTRA_PAYERS with PLAN_GROUPS array
 *    that iterates all 21 plan groups automatically — no manual column mapping needed
 *  - Each plan group: col = Alma, col+1 = Headway, col+2 = Grow Therapy, col+3 = SBH
 *  - intermediary_rates auto-generated across all 21 plans × all states
 *  - direct_rates (SBH) auto-generated using col+3 per plan group
 *  - Master data read extended to 90 columns (covers col 85 = last SBH col)
 *
 * HOW TO USE:
 * 1. In SLAVE Google Sheet → Extensions → Apps Script
 * 2. Replace ALL code with this, Save
 * 3. Run → syncRatesFromMaster
 * 4. Grant permissions if prompted (one-time)
 *
 * DOWNLOAD AFTER RUNNING:
 *   Tab "intermediary_rates" → File > Download > CSV  → upload to dashboard
 *   Tab "direct_rates"       → File > Download > CSV  → upload to dashboard
 *
 * NOTE ON PAYER NAMES:
 *   This script uses the new plan names (e.g. 'BCBS - of Massachusetts').
 *   If the dashboard already has rates under old names, re-import will create
 *   new payer records. Run a cleanup SQL on the DB after importing if needed.
 */

// ── !! UPDATE THIS to the new MASTER spreadsheet ID !! ────────
// Find it in the URL: docs.google.com/spreadsheets/d/[ID]/edit
var MASTER_SHEET_ID = '1pniFf18jZK9EU4ykUfh1CgLm0wBHCXHL1223eKeXH7Y';
var MASTER_TAB      = 'Rates';
var SLAVE_TAB       = 'intermediary_rates';
var DIRECT_TAB      = 'direct_rates';

// ── State block start rows in new MASTER (1-indexed, alphabetical) ──
// Confirmed: AK=3, AZ=11, CO=19, CT=27, DC=35 — each block = 8 rows
// KS / ME / VT exist in MASTER but are excluded from the tool export
var STATE_TO_ROW = {
  AK: 3,   AZ: 11,  CO: 19,  CT: 27,  DC: 35,  FL: 43,
  HI: 51,  IA: 59,  ID: 67,  MD: 83,  MN: 99,  MT: 107,
  ND: 115, NE: 123, NH: 131, NM: 139, NV: 147, OR: 155,
  SD: 163, UT: 171, WA: 187, WY: 195,
};

// ── CPT row offsets within each state block ───────────────────
// Row 0 = state label, Row 1 = date, Rows 2–6 = CPT codes
var CPT_OFFSET = { '99214': 2, '99215': 3, '90833': 4, '90836': 5, '90838': 6 };

// ── Plan groups — matches new MASTER column layout exactly ────
// col = 1-indexed Alma column; sub-cols: +0=Alma, +1=Headway, +2=Grow, +3=SBH
var PLAN_GROUPS = [
  { plan: 'Aetna',                                             col: 2  },
  { plan: 'Cigna',                                             col: 6  },
  { plan: 'UHC / Oscar / Optum',                               col: 10 },
  { plan: 'Carelon Behavioral Health',                         col: 14 },
  { plan: 'Ambetter',                                          col: 18 },
  { plan: 'BCBS - Florida Blue',                               col: 22 },
  { plan: 'BCBS - Florida Blue Medicare Advantage',            col: 26 },
  { plan: 'BCBS - of Arizona',                                 col: 30 },
  { plan: 'BCBS - of Massachusetts',                           col: 34 },
  { plan: 'BCBS - of Minnesota',                               col: 38 },
  { plan: 'BCBS - Anthem (Colorado)',                          col: 42 },
  { plan: 'BCBS - Anthem (Connecticut)',                       col: 46 },
  { plan: 'BCBS - Anthem (Indiana)',                           col: 50 },
  { plan: 'BCBS - Anthem (Maine)',                             col: 54 },
  { plan: 'BCBS - Anthem (Nevada)',                            col: 58 },
  { plan: 'BCBS - Anthem (New Hampshire)',                     col: 62 },
  { plan: 'BCBS - Horizon (New Jersey)',                       col: 66 },
  { plan: 'BCBS - Independence (Pennsylvania)',                col: 70 },
  { plan: 'BCBS - Premera (Washington)',                       col: 74 },
  { plan: 'BCBS - Regence (Washington)',                       col: 78 },
  { plan: 'BCBS - Wellmark',                                   col: 82 },
];

var INTERMEDIARIES = [
  { name: 'Alma',          offset: 0 },
  { name: 'Headway',       offset: 1 },
  { name: 'Grow Therapy',  offset: 2 },
];


// ══════════════════════════════════════════════════════════════
//  MAIN FUNCTION
// ══════════════════════════════════════════════════════════════

function syncRatesFromMaster() {
  if (MASTER_SHEET_ID === 'PASTE_NEW_MASTER_SHEET_ID_HERE') {
    SpreadsheetApp.getUi().alert(
      'Setup required:\n\n' +
      'Open populate_slave_v7.gs and replace\n' +
      'PASTE_NEW_MASTER_SHEET_ID_HERE\n' +
      'with the actual ID from the new MASTER sheet URL.'
    );
    return;
  }

  var masterSS    = SpreadsheetApp.openById(MASTER_SHEET_ID);
  var masterSheet = masterSS.getSheetByName(MASTER_TAB);
  // Read 210 rows × 90 cols — covers all 21 plan groups (last SBH col = 85)
  var masterData  = masterSheet.getRange(1, 1, 210, 90).getValues();

  var slaveSS = SpreadsheetApp.getActiveSpreadsheet();

  var intermediaryCount = _syncIntermediaryRates(slaveSS, masterData);
  var directCount       = _syncDirectRates(slaveSS, masterData);

  slaveSS.toast(
    intermediaryCount + ' intermediary rates synced → intermediary_rates tab\n' +
    directCount + ' direct billing rates synced → direct_rates tab\n\n' +
    'Download each tab as CSV and upload to the dashboard.',
    'Done!',
    12
  );
}


// ══════════════════════════════════════════════════════════════
//  INTERMEDIARY RATES (Alma / Headway / Grow Therapy)
// ══════════════════════════════════════════════════════════════

function _syncIntermediaryRates(slaveSS, masterData) {
  var sheet = slaveSS.getSheetByName(SLAVE_TAB);
  if (!sheet) { sheet = slaveSS.insertSheet(SLAVE_TAB); }
  sheet.clearContents();

  sheet.getRange(1, 1, 1, 6).setValues(
    [['intermediary_name', 'payer_name', 'cpt_code', 'state', 'allowed_amount', 'effective_date']]
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

      for (var ii = 0; ii < INTERMEDIARIES.length; ii++) {
        var intermediary = INTERMEDIARIES[ii];
        var colNum       = pg.col + intermediary.offset;  // 1-indexed

        // Effective date: date row = masterData[stateRow] (0-indexed)
        var dateRaw   = String(masterData[stateRow][colNum - 1] || '');
        var dateMatch = dateRaw.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
        var effDate   = '';
        if (dateMatch) {
          var yr  = dateMatch[3].length === 2 ? '20' + dateMatch[3] : dateMatch[3];
          effDate = yr + '-' + ('0' + dateMatch[1]).slice(-2) + '-' + ('0' + dateMatch[2]).slice(-2);
        }

        for (var ci = 0; ci < cptCodes.length; ci++) {
          var cpt       = cptCodes[ci];
          var masterRow = stateRow + CPT_OFFSET[cpt];        // 1-indexed
          var val       = masterData[masterRow - 1][colNum - 1]; // 0-indexed

          if (typeof val === 'number' && !isNaN(val) && val > 0) {
            outputRows.push([intermediary.name, pg.plan, cpt, state, val, effDate]);
            count++;
          }
        }
      }
    }
  }

  if (outputRows.length > 0) {
    sheet.getRange(2, 1, outputRows.length, 6).setValues(outputRows);
    sheet.getRange(2, 5, outputRows.length, 1).setNumberFormat('$#,##0.00');
  }

  return count;
}


// ══════════════════════════════════════════════════════════════
//  DIRECT RATES (SBH / Clinic Submit — col+3 per plan group)
// ══════════════════════════════════════════════════════════════

function _syncDirectRates(slaveSS, masterData) {
  var sheet = slaveSS.getSheetByName(DIRECT_TAB);
  if (!sheet) { sheet = slaveSS.insertSheet(DIRECT_TAB); }
  sheet.clearContents();

  sheet.getRange(1, 1, 1, 5).setValues(
    [['payer_name', 'cpt_code', 'state', 'allowed_amount', 'effective_date']]
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
      var sbhColNum = pg.col + 3;  // SBH is always col+3 within each plan group

      var dateRaw   = String(masterData[stateRow][sbhColNum - 1] || '');
      var dateMatch = dateRaw.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
      var effDate   = '';
      if (dateMatch) {
        var yr  = dateMatch[3].length === 2 ? '20' + dateMatch[3] : dateMatch[3];
        effDate = yr + '-' + ('0' + dateMatch[1]).slice(-2) + '-' + ('0' + dateMatch[2]).slice(-2);
      }

      for (var ci = 0; ci < cptCodes.length; ci++) {
        var cpt       = cptCodes[ci];
        var masterRow = stateRow + CPT_OFFSET[cpt];
        var val       = masterData[masterRow - 1][sbhColNum - 1];

        if (typeof val === 'number' && !isNaN(val) && val > 0) {
          outputRows.push([pg.plan, cpt, state, val, effDate]);
          count++;
        }
      }
    }
  }

  if (outputRows.length > 0) {
    sheet.getRange(2, 1, outputRows.length, 5).setValues(outputRows);
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
