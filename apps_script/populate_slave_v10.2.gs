/**
 * Solrei SLAVE – Rate Sync from MASTER (v10.2 — verified structure July 6 2026)
 *
 * Structure verified by live debug against MASTER_DATA tab.
 * Reads from MASTER_DATA tab (local IMPORTRANGE mirror of MASTER sheet).
 *
 * STATE BLOCK STRUCTURE (8 rows per state):
 *   Row N+0 = State label + payer group headers
 *   Row N+1 = Channel headers ([JJ] Alma MM/DD/YY, Headway MM/DD/YY, etc.)
 *   Row N+2 = 99214
 *   Row N+3 = 99215
 *   Row N+4 = 90833
 *   Row N+5 = 90836
 *   Row N+6 = 90838
 *   Row N+7 = blank
 *
 * CORE COLUMN GROUPS (fixed, every state):
 *   Cols 2-5:   Optum/UHC/Oscar
 *   Cols 6-9:   Aetna
 *   Cols 10-13: Cigna
 *   Cols 14-17: Carelon Behavioral Health
 *   Cols 18-21: Ambetter
 *   Cols 22-25: Blue Cross (plan name varies by state)
 *
 * HOW TO USE:
 * 1. SLAVE Sheet → Extensions → Apps Script
 * 2. Replace ALL code with this → Save
 * 3. Run → syncRatesFromMaster
 * 4. Download intermediary_rates tab as CSV → upload to dashboard
 */

var MASTER_TAB = 'MASTER_DATA';
var SLAVE_TAB  = 'intermediary_rates';
var DIRECT_TAB = 'direct_rates';

// ── State label rows (1-indexed) — verified July 6 2026 ───────
var STATE_TO_ROW = {
  AK:  3,  AZ: 11,  CO: 19,  CT: 27,  DC: 35,  FL: 43,
  HI: 51,  ID: 59,  IA: 67,  KS: 75,  ME: 83,  MD: 91,
  MN: 99,  MT:107,  NE:115,  NV:123,  NH:131,  NM:139,
  ND:147,  OR:155,  SD:163,  UT:171,  VT:179,  WA:187,
  WY:195,
};

// ── CPT offsets from state label row ─────────────────────────
// Label=N, Channel headers=N+1, CPT rows=N+2 through N+6
var CPT_OFFSET = { '99214': 2, '99215': 3, '90833': 4, '90836': 5, '90838': 6 };

// ── Core plan groups (fixed columns, same every state) ────────
// col = 1-indexed Alma column; +0=Alma, +1=Headway, +2=Grow, +3=SBH
var CORE_PLAN_GROUPS = [
  { plan: 'Optum/UHC/Oscar',           col: 2  },
  { plan: 'Aetna',                     col: 6  },
  { plan: 'Cigna',                     col: 10 },
  { plan: 'Carelon Behavioral Health', col: 14 },
  { plan: 'Ambetter',                  col: 18 },
  { plan: 'Blue Cross',                col: 22 }, // resolved per state
];

// ── Blue Cross plan name by state (col 22-25 group) ───────────
var BLUE_CROSS_BY_STATE = {
  AK: 'BCBS Massachusetts',         AZ: 'BCBS Massachusetts',
  CO: 'Anthem BCBS Colorado',        CT: 'Anthem BCBS Connecticut',
  DC: 'Blue Cross',                  FL: 'Florida Blue',
  HI: 'Blue Cross',                  ID: 'Blue Cross',
  IA: 'BCBS Massachusetts',          KS: 'Blue Cross',
  ME: 'Anthem BCBS Maine',           MD: 'Blue Cross',
  MN: 'BCBS Massachusetts',          MT: 'Blue Cross',
  NE: 'Blue Cross',                  NV: 'Anthem BCBS Nevada',
  NH: 'Anthem BCBS New Hampshire',   NM: 'BCBS Massachusetts',
  ND: 'Blue Cross',                  OR: 'BCBS Massachusetts',
  SD: 'Blue Cross',                  UT: 'Blue Cross',
  VT: 'Blue Cross',                  WA: 'BCBS Massachusetts',
  WY: 'Blue Cross',
};

// ── State-specific extra columns ─────────────────────────────
// Verified from debugExtraCols() July 6 2026
var STATE_EXTRA_COLS = {
  AK: [
    { col: 28, intermediary: 'Headway', provider: 'JJ', plan: 'Horizon BCBS New Jersey'      },
    { col: 29, intermediary: 'Headway', provider: 'JJ', plan: 'Independence Blue Cross PA'   },
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
  ],
  AZ: [
    { col: 26, intermediary: 'Headway', provider: 'JJ', plan: 'BCBS Arizona'                 },
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
  ],
  CO: [
    { col: 27, intermediary: 'Headway', provider: 'JJ', plan: 'Anthem BCBS Colorado'         },
  ],
  FL: [
    { col: 28, intermediary: 'Headway', provider: 'KR', plan: 'Horizon BCBS New Jersey'      },
    { col: 29, intermediary: 'Headway', provider: '',   plan: 'Independence Blue Cross PA'   },
    { col: 31, intermediary: 'Headway', provider: 'JJ', plan: 'Providence Health Plan'       },
    { col: 34, intermediary: 'Headway', provider: 'JJ', plan: 'BCBS Massachusetts'           },
    { col: 35, intermediary: 'Headway', provider: 'JJ', plan: 'Florida Blue Medicare Advantage' },
  ],
  IA: [
    { col: 33, intermediary: 'SBH',     provider: 'JJ', plan: 'Wellmark Iowa'                },
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
  ],
  ME: [
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
  ],
  MN: [
    { col: 26, intermediary: 'Headway', provider: 'JJ', plan: 'BCBS Minnesota'               },
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
    { col: 35, intermediary: 'Headway', provider: 'JJ', plan: 'BCBS Minnesota Medicaid'      },
  ],
  NM: [
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
  ],
  OR: [
    { col: 32, intermediary: 'Headway', provider: '',   plan: 'Regence BCBS Oregon'           },
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
  ],
  WA: [
    { col: 28, intermediary: 'Headway', provider: 'KR', plan: 'Horizon BCBS New Jersey'      },
    { col: 29, intermediary: 'Headway', provider: 'KR', plan: 'Independence Blue Cross PA'   },
    { col: 30, intermediary: 'Headway', provider: 'KR', plan: 'Premera Blue Cross Washington'},
    { col: 32, intermediary: 'Headway', provider: '',   plan: 'Regence Blue Shield Washington'},
    { col: 34, intermediary: 'Alma',    provider: 'JJ', plan: 'BCBS Massachusetts'            },
  ],
};

// Add BCBS Massachusetts Alma for remaining states that have col 34 data
// These states appear in the debug with col34=[JJ] Alma BCBS Massachusetts
var BCBS_MA_STATES = ['AK','AZ','IA','ME','MN','NM','OR','WA'];

// ── Channels ──────────────────────────────────────────────────
var CHANNELS = [
  { name: 'Alma',         offset: 0 },
  { name: 'Headway',      offset: 1 },
  { name: 'Grow Therapy', offset: 2 },
  { name: 'SBH',          offset: 3 },
];


// ══════════════════════════════════════════════════════════════
//  HELPERS
// ══════════════════════════════════════════════════════════════

function _parseProvider(cellText) {
  var text = String(cellText || '').trim();
  var match = text.match(/^\[([A-Z]{2,3})\]/);
  return match ? match[1] : '';
}

function _parseDate(cellText) {
  var text = String(cellText || '');
  var match = text.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
  if (!match) return '';
  var yr = match[3].length === 2 ? '20' + match[3] : match[3];
  return yr + '-' + ('0' + match[1]).slice(-2) + '-' + ('0' + match[2]).slice(-2);
}

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
//  MAIN
// ══════════════════════════════════════════════════════════════

function syncRatesFromMaster() {
  var masterSheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MASTER_TAB);
  if (!masterSheet) {
    SpreadsheetApp.getUi().alert('MASTER_DATA tab not found. Check IMPORTRANGE formula.');
    return;
  }
  var masterData = masterSheet.getRange(1, 1, 220, 36).getValues();

  var slaveSS = SpreadsheetApp.getActiveSpreadsheet();
  var intermediaryCount = _syncIntermediaryRates(slaveSS, masterData);
  var directCount       = _syncDirectRatesBackup(slaveSS, masterData);

  slaveSS.toast(
    intermediaryCount + ' rates → intermediary_rates tab\n' +
    '(Alma · Headway · Grow Therapy · SBH Clinic Submit)\n\n' +
    directCount + ' SBH rates → direct_rates tab\n\n' +
    'Download intermediary_rates CSV → upload to dashboard.',
    'Sync Complete — v10.2', 15
  );
}


// ══════════════════════════════════════════════════════════════
//  INTERMEDIARY RATES
// ══════════════════════════════════════════════════════════════

function _syncIntermediaryRates(slaveSS, masterData) {
  var sheet = slaveSS.getSheetByName(SLAVE_TAB);
  if (!sheet) { sheet = slaveSS.insertSheet(SLAVE_TAB); }
  sheet.clearContents();

  sheet.getRange(1, 1, 1, 7).setValues([[
    'intermediary_name','payer_name','cpt_code','state',
    'allowed_amount','effective_date','provider'
  ]]);

  var outputRows = [];
  var states     = Object.keys(STATE_TO_ROW);
  var cptCodes   = Object.keys(CPT_OFFSET);

  for (var si = 0; si < states.length; si++) {
    var state      = states[si];
    var stateRow   = STATE_TO_ROW[state];      // 1-indexed label row
    var hdrRowIdx  = stateRow;                 // 0-indexed channel header row (label+1)
    // Note: masterData is 0-indexed, stateRow is 1-indexed
    // Label = masterData[stateRow-1], Header = masterData[stateRow], CPT = masterData[stateRow+offset]

    // ── Core plan groups ──────────────────────────────────────
    for (var pi = 0; pi < CORE_PLAN_GROUPS.length; pi++) {
      var pg       = CORE_PLAN_GROUPS[pi];
      var planName = pg.plan === 'Blue Cross'
                     ? (BLUE_CROSS_BY_STATE[state] || 'Blue Cross')
                     : pg.plan;

      for (var ci = 0; ci < CHANNELS.length; ci++) {
        var channel = CHANNELS[ci];
        var colIdx  = pg.col + channel.offset - 1;  // 0-indexed

        var headerCell = masterData[hdrRowIdx][colIdx];
        var provider   = _parseProvider(headerCell);
        var effDate    = _parseDate(headerCell);

        for (var ki = 0; ki < cptCodes.length; ki++) {
          var cpt        = cptCodes[ki];
          var dataRowIdx = stateRow + CPT_OFFSET[cpt] - 1;
          var val        = masterData[dataRowIdx][colIdx];
          var rate       = _parseRate(val);

          if (rate !== null) {
            outputRows.push([channel.name, planName, cpt, state,
                             rate, effDate, provider]);
          }
        }
      }
    }

    // ── State-specific extra columns ──────────────────────────
    var extras = STATE_EXTRA_COLS[state] || [];
    for (var ei = 0; ei < extras.length; ei++) {
      var ex     = extras[ei];
      var colIdx = ex.col - 1;

      var headerCell = masterData[hdrRowIdx][colIdx];
      var effDate    = _parseDate(headerCell);

      for (var ki = 0; ki < cptCodes.length; ki++) {
        var cpt        = cptCodes[ki];
        var dataRowIdx = stateRow + CPT_OFFSET[cpt] - 1;
        var val        = masterData[dataRowIdx][colIdx];
        var rate       = _parseRate(val);

        if (rate !== null) {
          outputRows.push([ex.intermediary, ex.plan, cpt, state,
                           rate, effDate, ex.provider]);
        }
      }
    }
  }

  Logger.log('Total rows: ' + outputRows.length);

  if (outputRows.length > 0) {
    sheet.getRange(2, 1, outputRows.length, 7).setValues(outputRows);
    sheet.getRange(2, 5, outputRows.length, 1).setNumberFormat('$#,##0.00');
  }
  return outputRows.length;
}


// ══════════════════════════════════════════════════════════════
//  DIRECT RATES BACKUP (SBH only — reference tab)
// ══════════════════════════════════════════════════════════════

function _syncDirectRatesBackup(slaveSS, masterData) {
  var sheet = slaveSS.getSheetByName(DIRECT_TAB);
  if (!sheet) { sheet = slaveSS.insertSheet(DIRECT_TAB); }
  sheet.clearContents();

  sheet.getRange(1, 1, 1, 6).setValues([[
    'payer_name','cpt_code','state','allowed_amount','effective_date','provider'
  ]]);

  var outputRows = [];
  var states     = Object.keys(STATE_TO_ROW);
  var cptCodes   = Object.keys(CPT_OFFSET);

  for (var si = 0; si < states.length; si++) {
    var state      = states[si];
    var stateRow   = STATE_TO_ROW[state];
    var hdrRowIdx  = stateRow;

    // SBH from core groups (col+3)
    for (var pi = 0; pi < CORE_PLAN_GROUPS.length; pi++) {
      var pg       = CORE_PLAN_GROUPS[pi];
      var planName = pg.plan === 'Blue Cross'
                     ? (BLUE_CROSS_BY_STATE[state] || 'Blue Cross')
                     : pg.plan;
      var colIdx   = pg.col + 3 - 1;

      var headerCell = masterData[hdrRowIdx][colIdx];
      var provider   = _parseProvider(headerCell);
      var effDate    = _parseDate(headerCell);

      for (var ki = 0; ki < cptCodes.length; ki++) {
        var cpt        = cptCodes[ki];
        var dataRowIdx = stateRow + CPT_OFFSET[cpt] - 1;
        var val        = masterData[dataRowIdx][colIdx];
        var rate       = _parseRate(val);
        if (rate !== null) {
          outputRows.push([planName, cpt, state, rate, effDate, provider]);
        }
      }
    }

    // SBH from extra cols (Wellmark Iowa, etc.)
    var extras = STATE_EXTRA_COLS[state] || [];
    for (var ei = 0; ei < extras.length; ei++) {
      var ex = extras[ei];
      if (ex.intermediary !== 'SBH') continue;
      var colIdx     = ex.col - 1;
      var headerCell = masterData[hdrRowIdx][colIdx];
      var effDate    = _parseDate(headerCell);

      for (var ki = 0; ki < cptCodes.length; ki++) {
        var cpt        = cptCodes[ki];
        var dataRowIdx = stateRow + CPT_OFFSET[cpt] - 1;
        var val        = masterData[dataRowIdx][colIdx];
        var rate       = _parseRate(val);
        if (rate !== null) {
          outputRows.push([ex.plan, cpt, state, rate, effDate, ex.provider]);
        }
      }
    }
  }

  if (outputRows.length > 0) {
    sheet.getRange(2, 1, outputRows.length, 6).setValues(outputRows);
    sheet.getRange(2, 4, outputRows.length, 1).setNumberFormat('$#,##0.00');
  }
  return outputRows.length;
}


// ══════════════════════════════════════════════════════════════
//  DEBUG HELPERS
// ══════════════════════════════════════════════════════════════

function debugAllStatesNew() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MASTER_TAB);
  var data  = sheet.getRange(1, 1, 320, 1).getValues();
  for (var i = 0; i < 320; i++) {
    var cell = String(data[i][0]).trim();
    if (cell && cell !== '99214' && cell !== '99215' &&
        cell !== '90833' && cell !== '90836' && cell !== '90838') {
      Logger.log('Row ' + (i+1) + ': ' + cell.substring(0, 35));
    }
  }
}

function debugColumnsNew() {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MASTER_TAB);
  var data  = sheet.getRange(4, 1, 1, 36).getValues()[0];
  for (var i = 0; i < 36; i++) {
    var cell = String(data[i]).trim();
    if (cell && cell !== '0') {
      Logger.log('Col ' + (i+1) + ': ' + cell.substring(0, 60));
    }
  }
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
