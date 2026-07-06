/**
 * Solrei SLAVE – Rate Sync from MASTER (v6 — state-specific payer mapping)
 *
 * Changes from v5:
 *  - _syncIntermediaryRates now AUTO-GENERATES all rows (no template required)
 *  - Replaced global PAYER_COL with BASE_PAYERS + STATE_EXTRA_PAYERS structure
 *    so each state can have different payers in the same column positions
 *  - Adds CT (Connecticut) and UT (Utah) as new states
 *  - Adds all missing BCBS/Anthem/Regence/Premera/Horizon/Independence plans
 *    per state per the MASTER sheet layout
 *  - direct_rates sync unchanged from v5
 *
 * HOW TO USE:
 * 1. In SLAVE Google Sheet → Extensions → Apps Script
 * 2. Replace ALL code with this, Save
 * 3. Run → syncRatesFromMaster
 * 4. Grant permissions if prompted (one-time)
 * 5. Done in ~15–30 seconds — syncs both intermediary AND direct rates
 *
 * DOWNLOAD AFTER RUNNING:
 *   Tab "intermediary_rates" → File > Download > CSV  → upload to dashboard
 *   Tab "direct_rates"       → File > Download > CSV  → upload to dashboard
 */

var MASTER_SHEET_ID = '1QyfSpVlAba_epE1eehN5wlU1543AGWEpIzmsGPNlgXE';
var MASTER_TAB      = 'Rates';
var SLAVE_TAB       = 'intermediary_rates';
var DIRECT_TAB      = 'direct_rates';

// ── State block start rows in MASTER (1-indexed) ──────────────
var STATE_TO_ROW = {
  AK:3,  AZ:11, CO:19,  FL:27,  HI:35,  ID:43,  IA:51,  MD:59,
  MN:67, MT:75, NE:83,  NV:91,  NM:99,  ND:107, OR:115, SD:123,
  WA:131,DC:139,WY:147, NH:163, CT:187, UT:195
};

// ── CPT row offsets within each state block ───────────────────
var CPT_OFFSET = {'99214':2,'99215':3,'90833':4,'90836':5,'90838':6};

// ── Base payers: same column across ALL states ────────────────
// Each entry: [payer_name, intermediary, master_column (1-indexed)]
var BASE_PAYERS = [
  ['UHC/Oscar/Optum',   'Alma',          2],
  ['UHC/Oscar/Optum',   'Headway',       3],
  ['UHC/Oscar/Optum',   'Grow Therapy',  4],
  ['Aetna',             'Alma',          6],
  ['Aetna',             'Headway',       7],
  ['Aetna',             'Grow Therapy',  8],
  ['Cigna',             'Alma',         10],
  ['Cigna',             'Headway',      11],
  ['Cigna',             'Grow Therapy', 12],
];

// ── State-specific extra payers (col N=14 onward varies by state) ─
// Each entry: [payer_name, intermediary, master_column (1-indexed)]
var STATE_EXTRA_PAYERS = {
  'AK': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
    ['Horizon Blue Cross and Blue Shield of New Jersey',      'Headway', 18],
    ['Independence Blue Cross Pennsylvania',                  'Headway', 19],
  ],
  'AZ': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
    ['Blue Cross Blue Shield of Arizona',                     'Headway', 18],
  ],
  'CO': [
    ['Anthem Blue Cross and Blue Shield',                     'Alma',    14],
    ['Anthem Blue Cross and Blue Shield Colorado HMO',        'Headway', 18],
    ['Anthem Blue Cross and Blue Shield Colorado PPO',        'Headway', 19],
  ],
  'FL': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
    ['Florida Blue',                                          'Headway', 19],
    ['Florida Blue Medicare Advantage',                       'Headway', 20],
    ['Horizon Blue Cross and Blue Shield of New Jersey',      'Headway', 21],
    ['Independence Blue Cross Pennsylvania',                  'Headway', 22],
    ['Anthem Blue Cross and Blue Shield Indiana',             'Headway', 23],
  ],
  'IA': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
  ],
  'MN': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
    ['Blue Cross and Blue Shield of Minnesota',               'Headway', 18],
    ['Blue Cross and Blue Shield of Minnesota Medicaid',      'Headway', 19],
    ['Blue Cross and Blue Shield of Minnesota Medicare Advantage', 'Headway', 20],
  ],
  'NV': [
    ['Anthem Blue Cross and Blue Shield',                     'Alma',    14],
  ],
  'NH': [
    ['Anthem Blue Cross and Blue Shield',                     'Alma',    14],
    ['Premera Blue Cross Washington',                         'Headway', 18],
  ],
  'NM': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
  ],
  'OR': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
    ['Regence BlueCross BlueShield of Oregon',                'Headway', 18],
  ],
  'WA': [
    ['Blue Cross Blue Shield of Massachusetts',               'Alma',    14],
    ['Blue Cross Blue Shield of Massachusetts',               'Headway', 18],
    ['Horizon Blue Cross and Blue Shield of New Jersey',      'Headway', 19],
    ['Independence Blue Cross Pennsylvania',                  'Headway', 20],
    ['Regence BlueShield of Washington',                      'Headway', 21],
    ['Premera Blue Cross Washington',                         'Headway', 22],
  ],
  'CT': [
    ['Anthem Blue Cross and Blue Shield',                     'Alma',    14],
  ],
  // HI, ID, MD, MT, NE, ND, SD, DC, WY, KS, VT, UT — base payers only
};

// ── SBH (clinic-submit / direct billing) column mapping (1-indexed) ──
var SBH_COL = {
  'Optum/UHC/Oscar':                        5,
  'Aetna':                                  9,
  'Cigna':                                 13,
  'Blue Cross Blue Shield of Massachusetts': 17
};


// ══════════════════════════════════════════════════════════════
//  MAIN FUNCTION
// ══════════════════════════════════════════════════════════════

function syncRatesFromMaster() {
  var masterSS    = SpreadsheetApp.openById(MASTER_SHEET_ID);
  var masterSheet = masterSS.getSheetByName(MASTER_TAB);
  // Read 210 rows to cover UT (row 195) + CPT offsets up to 6 = row 201
  var masterData  = masterSheet.getRange(1, 1, 210, 30).getValues();

  var slaveSS = SpreadsheetApp.getActiveSpreadsheet();

  var intermediaryCount = _syncIntermediaryRates(slaveSS, masterData);
  var directCount       = _syncDirectRates(slaveSS, masterData);

  slaveSS.toast(
    intermediaryCount + ' intermediary rates synced (intermediary_rates tab)\n' +
    directCount + ' direct billing rates synced (direct_rates tab)\n\n' +
    'Download each tab as CSV and upload to the dashboard.',
    'Done!',
    12
  );
}


// ══════════════════════════════════════════════════════════════
//  INTERMEDIARY RATES — auto-generated from MASTER
// ══════════════════════════════════════════════════════════════

function _syncIntermediaryRates(slaveSS, masterData) {
  // Get or create the tab
  var sheet = slaveSS.getSheetByName(SLAVE_TAB);
  if (!sheet) { sheet = slaveSS.insertSheet(SLAVE_TAB); }
  sheet.clearContents();

  // Write header (matches dashboard import format)
  sheet.getRange(1, 1, 1, 6).setValues(
    [['intermediary_name','payer_name','cpt_code','state','allowed_amount','effective_date']]
  );

  var outputRows = [];
  var count      = 0;
  var states     = Object.keys(STATE_TO_ROW);
  var cptCodes   = Object.keys(CPT_OFFSET);

  for (var si = 0; si < states.length; si++) {
    var state    = states[si];
    var stateRow = STATE_TO_ROW[state];  // 1-indexed; masterData[stateRow] = date header row

    // Combine base payers with any state-specific extras
    var payers = BASE_PAYERS.slice();
    if (STATE_EXTRA_PAYERS[state]) {
      payers = payers.concat(STATE_EXTRA_PAYERS[state]);
    }

    for (var pi = 0; pi < payers.length; pi++) {
      var payerName    = payers[pi][0];
      var intermediary = payers[pi][1];
      var colNum       = payers[pi][2];  // 1-indexed

      // Effective date lives in the date-header row (stateRow+1 in 1-indexed = masterData[stateRow])
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
        var val       = masterData[masterRow - 1][colNum - 1];  // 0-indexed

        if (typeof val === 'number' && !isNaN(val) && val > 0) {
          outputRows.push([intermediary, payerName, cpt, state, val, effDate]);
          count++;
        }
      }
    }
  }

  if (outputRows.length > 0) {
    sheet.getRange(2, 1, outputRows.length, 6).setValues(outputRows);
    // Format amount column as currency for readability
    sheet.getRange(2, 5, outputRows.length, 1).setNumberFormat('$#,##0.00');
  }

  return count;
}


// ══════════════════════════════════════════════════════════════
//  DIRECT RATES (SBH / Clinic Submit — Jodene Jensen)
// ══════════════════════════════════════════════════════════════

function _syncDirectRates(slaveSS, masterData) {
  var directSheet = slaveSS.getSheetByName(DIRECT_TAB);
  if (!directSheet) { directSheet = slaveSS.insertSheet(DIRECT_TAB); }
  directSheet.clearContents();

  directSheet.getRange(1, 1, 1, 5).setValues(
    [['payer_name','cpt_code','state','allowed_amount','effective_date']]
  );

  var outputRows = [];
  var count      = 0;
  var states     = Object.keys(STATE_TO_ROW);
  var cptCodes   = Object.keys(CPT_OFFSET);
  var sbhPayers  = Object.keys(SBH_COL);

  for (var si = 0; si < states.length; si++) {
    var state    = states[si];
    var stateRow = STATE_TO_ROW[state];

    for (var pi = 0; pi < sbhPayers.length; pi++) {
      var payerName = sbhPayers[pi];
      var sbhColNum = SBH_COL[payerName];

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
          outputRows.push([payerName, cpt, state, val, effDate]);
          count++;
        }
      }
    }
  }

  if (outputRows.length > 0) {
    directSheet.getRange(2, 1, outputRows.length, 5).setValues(outputRows);
    directSheet.getRange(2, 4, outputRows.length, 1).setNumberFormat('$#,##0.00');
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
