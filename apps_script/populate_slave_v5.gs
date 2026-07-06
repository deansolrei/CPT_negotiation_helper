/**
 * Solrei SLAVE – Rate Sync from MASTER (v5 — adds SBH / Direct Billing)
 *
 * Changes from v4:
 *  - Reads SBH (clinic-submit) columns from MASTER and writes a
 *    "direct_rates" tab in SLAVE (payer_name | cpt_code | state | allowed_amount | effective_date)
 *  - Existing intermediary_rates sync is unchanged
 *
 * HOW TO USE:
 * 1. In SLAVE Google Sheet → Extensions → Apps Script
 * 2. Replace ALL code with this, Save
 * 3. Run → syncRatesFromMaster
 * 4. Grant permissions if prompted (one-time)
 * 5. Done in ~15 seconds — syncs both intermediary AND direct rates
 *
 * TO RE-RUN AFTER UPDATING MASTER:
 * Click Run → syncRatesFromMaster  (or use the Solrei Rates menu)
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
  AK:3,  AZ:11, CO:19, FL:27, HI:35,  ID:43,  IA:51,  MD:59,
  MN:67, MT:75, NE:83, NV:91, NM:99,  ND:107, OR:115, SD:123,
  WA:131,DC:139,WY:147,KS:155,NH:163, ME:171, VT:179, CT:187, UT:195
};

// ── CPT row offsets within each state block ───────────────────
var CPT_OFFSET = {'99214':2,'99215':3,'90833':4,'90836':5,'90838':6};

// ── Intermediary rate column mapping (1-indexed) ──────────────
// Key: 'PayerName|Intermediary'  Value: column number in MASTER
var PAYER_COL = {
  'UHC/Oscar/Optum|Alma':2,        'UHC/Oscar/Optum|Headway':3,   'UHC/Oscar/Optum|Grow Therapy':4,
  'Aetna|Alma':6,                  'Aetna|Headway':7,             'Aetna|Grow Therapy':8,
  'Cigna|Alma':10,                 'Cigna|Headway':11,            'Cigna|Grow Therapy':12,
  'Florida Blue|Alma':14,          'Florida Blue|Headway':15,     'Florida Blue|Grow Therapy':16,
  'BCBS - Massachusetts (virtual network)|Headway':18,
  'Horizon Blue Cross Blue Shield of New Jersey|Headway':18,
  'Independence Blue Cross Pennsylvania|Headway':19
};

// ── SBH (clinic-submit / direct billing) column mapping (1-indexed) ──
// Key: payer_name displayed in direct_rates tab  Value: MASTER column
var SBH_COL = {
  'Optum/UHC/Oscar':                       5,
  'Aetna':                                 9,
  'Cigna':                                13,
  'BCBS - Massachusetts (virtual network)':17
};

// ── State restrictions for certain payers ────────────────────
var PAYER_STATES = {
  'Florida Blue':                            ['FL'],
  'BCBS - Massachusetts (virtual network)':  ['FL','WA'],
  'Horizon Blue Cross Blue Shield of New Jersey': ['DC','MD'],
  'Independence Blue Cross Pennsylvania':         ['DC','MD']
};


// ══════════════════════════════════════════════════════════════
//  MAIN FUNCTION
// ══════════════════════════════════════════════════════════════

function syncRatesFromMaster() {
  // 1. Load MASTER data (single read call)
  var masterSS    = SpreadsheetApp.openById(MASTER_SHEET_ID);
  var masterSheet = masterSS.getSheetByName(MASTER_TAB);
  var masterData  = masterSheet.getRange(1, 1, 210, 30).getValues();

  var slaveSS = SpreadsheetApp.getActiveSpreadsheet();

  // 2. Sync intermediary rates (unchanged from v4)
  var intermediaryCount = _syncIntermediaryRates(slaveSS, masterData);

  // 3. Sync direct/SBH rates (new in v5)
  var directCount = _syncDirectRates(slaveSS, masterData);

  SpreadsheetApp.getActiveSpreadsheet().toast(
    intermediaryCount + ' intermediary rates synced\n' +
    directCount + ' direct billing rates synced\n' +
    'Download each tab as CSV and upload to the dashboard.',
    'Done!',
    10
  );
}


// ══════════════════════════════════════════════════════════════
//  INTERMEDIARY RATES (Alma / Headway / Grow Therapy)
// ══════════════════════════════════════════════════════════════

function _syncIntermediaryRates(slaveSS, masterData) {
  var slaveSheet = slaveSS.getSheetByName(SLAVE_TAB);
  if (!slaveSheet) { SpreadsheetApp.getActiveSpreadsheet().toast('Tab not found: ' + SLAVE_TAB, 'Error', 5); return 0; }

  var lastRow   = slaveSheet.getLastRow();
  var slaveData = slaveSheet.getRange(1, 1, lastRow, 4).getValues();

  var amtOut  = [];
  var dateOut = [];
  var count   = 0;

  for (var i = 0; i < slaveData.length; i++) {
    var intermediary = slaveData[i][0];
    var payer        = slaveData[i][1];
    var cpt          = String(parseInt(slaveData[i][2]));
    var state        = String(slaveData[i][3] || 'FL').toUpperCase();

    var valid = (intermediary === 'Alma' || intermediary === 'Headway' || intermediary === 'Grow Therapy');
    if (!valid || !STATE_TO_ROW[state] || !CPT_OFFSET[cpt]) {
      amtOut.push(['']); dateOut.push(['']); continue;
    }
    if (PAYER_STATES[payer] && PAYER_STATES[payer].indexOf(state) === -1) {
      amtOut.push(['']); dateOut.push(['']); continue;
    }

    var col = PAYER_COL[payer + '|' + intermediary];
    if (!col) { amtOut.push(['']); dateOut.push(['']); continue; }

    var masterRow = STATE_TO_ROW[state] + CPT_OFFSET[cpt];
    var val       = masterData[masterRow - 1][col - 1];

    if (typeof val === 'number' && !isNaN(val)) {
      amtOut.push([val]);
      count++;
    } else {
      amtOut.push(['']);
    }

    var dateRaw   = String(masterData[STATE_TO_ROW[state]][col - 1] || '');
    var dateMatch = dateRaw.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
    if (dateMatch) {
      var yr = dateMatch[3].length === 2 ? '20' + dateMatch[3] : dateMatch[3];
      dateOut.push([yr + '-' + ('0'+dateMatch[1]).slice(-2) + '-' + ('0'+dateMatch[2]).slice(-2)]);
    } else {
      dateOut.push(['']);
    }
  }

  slaveSheet.getRange(1, 5, lastRow, 1).setValues(amtOut);
  slaveSheet.getRange(1, 6, lastRow, 1).setValues(dateOut);

  return count;
}


// ══════════════════════════════════════════════════════════════
//  DIRECT RATES (SBH / Clinic Submit — Jodene Jensen)
// ══════════════════════════════════════════════════════════════

function _syncDirectRates(slaveSS, masterData) {
  // Get or create the direct_rates tab
  var directSheet = slaveSS.getSheetByName(DIRECT_TAB);
  if (!directSheet) {
    directSheet = slaveSS.insertSheet(DIRECT_TAB);
  }
  directSheet.clearContents();

  // Write header
  var headers = [['payer_name','cpt_code','state','allowed_amount','effective_date']];
  directSheet.getRange(1, 1, 1, 5).setValues(headers);

  var outputRows = [];
  var count = 0;

  var states    = Object.keys(STATE_TO_ROW);
  var cptCodes  = Object.keys(CPT_OFFSET);
  var sbhPayers = Object.keys(SBH_COL);

  for (var si = 0; si < states.length; si++) {
    var state    = states[si];
    var stateRow = STATE_TO_ROW[state];  // 1-indexed

    for (var pi = 0; pi < sbhPayers.length; pi++) {
      var payerName = sbhPayers[pi];
      var sbhColNum = SBH_COL[payerName];  // 1-indexed

      // Get effective date from the date header row of this state block
      var dateRaw   = String(masterData[stateRow][sbhColNum - 1] || '');
      var dateMatch = dateRaw.match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
      var effDate   = '';
      if (dateMatch) {
        var yr = dateMatch[3].length === 2 ? '20' + dateMatch[3] : dateMatch[3];
        effDate = yr + '-' + ('0'+dateMatch[1]).slice(-2) + '-' + ('0'+dateMatch[2]).slice(-2);
      }

      for (var ci = 0; ci < cptCodes.length; ci++) {
        var cpt       = cptCodes[ci];
        var masterRow = stateRow + CPT_OFFSET[cpt];
        var val       = masterData[masterRow - 1][sbhColNum - 1];

        // Only write numeric values (skip blanks, 'x', 'N/A', etc.)
        if (typeof val === 'number' && !isNaN(val) && val > 0) {
          outputRows.push([payerName, cpt, state, val, effDate]);
          count++;
        }
      }
    }
  }

  if (outputRows.length > 0) {
    directSheet.getRange(2, 1, outputRows.length, 5).setValues(outputRows);
  }

  // Format the amount column as currency
  if (outputRows.length > 0) {
    directSheet.getRange(2, 4, outputRows.length, 1)
      .setNumberFormat('$#,##0.00');
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
