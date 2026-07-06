/**
 * Solrei CPT Dashboard — New MASTER Google Sheet Builder (v3)
 *
 * Structure:
 *  Cols A–DA (1–105):  26 insurance plan groups × 4 sub-cols (Alma | Headway | Grow | SBH)
 *  Col  DB   (106):    State name — repeated on every row for easy reading at far right
 *  Col  DC   (107):    Medicare — Standard rate
 *  Col  DD   (108):    Medicare — Region 1
 *  Col  DE   (109):    Medicare — Region 2
 *  Cols DF–DK (110–115): 6 blank user columns
 *
 * Plan order (26 groups):
 *   Aetna → Cigna → UHC → Carelon → Ambetter → Ambetter (Washington) →
 *   BCBS FL Blue → FL Blue MA → BCBS AZ → BCBS MA → BCBS MN →
 *   BCBS MN Medicaid → BCBS MN Medicaid Advantage →
 *   Anthem CO HMO → Anthem CO PPO → Anthem CT → Anthem IN → Anthem ME →
 *   Anthem NV → Anthem NH → Horizon NJ → Independence PA →
 *   Premera WA → Regence WA → Regence OR → Wellmark Iowa
 *
 * Migrates data from current v2 MASTER (21 plans).
 * Bold vertical borders between main insurance sections.
 * Green conditional formatting = highest rate per 4-col insurance group per row.
 * User cols (DF–DK) are left white — no blue banner in those columns.
 *
 * HOW TO USE:
 * 1. Open any Google Sheet → Extensions → Apps Script
 * 2. Paste this entire script, Save (Ctrl+S)
 * 3. Run → buildNewMasterSheet
 * 4. Grant permissions when prompted (one-time)
 * 5. New spreadsheet URL appears in an alert dialog when done
 *
 * Old v2 MASTER is NOT modified. Estimated runtime: 5–8 minutes.
 */

// ── Source: v2 MASTER to migrate data FROM ────────────────────
var OLD_MASTER_ID  = '1pniFf18jZK9EU4ykUfh1CgLm0wBHCXHL1223eKeXH7Y';
var OLD_MASTER_TAB = 'Rates';

// ── CPT codes and row offsets within each state block ─────────
// Block layout: row 0 = state label, row 1 = date, rows 2–6 = CPTs, row 7 = blank gap
var CPT_CODES   = ['99214', '99215', '90833', '90836', '90838'];
var CPT_OFFSETS = { '99214': 2, '99215': 3, '90833': 4, '90836': 5, '90838': 6 };

// ── States (alphabetical, 25 total) ───────────────────────────
// KS / ME / VT kept in MASTER but excluded from dashboard tool export
var STATES = [
  ['AK', 'Alaska'],         ['AZ', 'Arizona'],       ['CO', 'Colorado'],
  ['CT', 'Connecticut'],    ['DC', 'Washington DC'],  ['FL', 'Florida'],
  ['HI', 'Hawaii'],         ['IA', 'Iowa'],           ['ID', 'Idaho'],
  ['KS', 'Kansas'],         ['MD', 'Maryland'],       ['ME', 'Maine'],
  ['MN', 'Minnesota'],      ['MT', 'Montana'],        ['ND', 'North Dakota'],
  ['NE', 'Nebraska'],       ['NH', 'New Hampshire'],  ['NM', 'New Mexico'],
  ['NV', 'Nevada'],         ['OR', 'Oregon'],         ['SD', 'South Dakota'],
  ['UT', 'Utah'],           ['VT', 'Vermont'],        ['WA', 'Washington'],
  ['WY', 'Wyoming'],
];

// ── Insurance plan groups (26 total) ─────────────────────────
// col: 1-indexed starting column of each 4-col group
// Sub-columns: col=Alma, col+1=Headway, col+2=Grow Therapy, col+3=SBH
var PLAN_GROUPS = [
  // ── Aetna ─────────────────────────────────────────────────
  { plan: 'Aetna',                                             family: 'Aetna',    col: 2   },
  // ── Cigna ─────────────────────────────────────────────────
  { plan: 'Cigna',                                             family: 'Cigna',    col: 6   },
  // ── UHC / Oscar / Optum ───────────────────────────────────
  { plan: 'UHC / Oscar / Optum',                               family: 'UHC',      col: 10  },
  // ── Carelon ───────────────────────────────────────────────
  { plan: 'Carelon Behavioral Health',                         family: 'Carelon',  col: 14  },
  // ── Ambetter (2 sub-plans) ────────────────────────────────
  { plan: 'Ambetter',                                          family: 'Ambetter', col: 18  },
  { plan: 'Ambetter (Washington)',                             family: 'Ambetter', col: 22  },
  // ── BCBS / Blue family (20 sub-plans) ────────────────────
  { plan: 'BCBS - Florida Blue',                               family: 'BCBS',     col: 26  },
  { plan: 'BCBS - Florida Blue Medicare Advantage',            family: 'BCBS',     col: 30  },
  { plan: 'BCBS - of Arizona',                                 family: 'BCBS',     col: 34  },
  { plan: 'BCBS - of Massachusetts',                           family: 'BCBS',     col: 38  },
  { plan: 'BCBS - of Minnesota',                               family: 'BCBS',     col: 42  },
  { plan: 'BCBS - Minnesota Medicaid',                         family: 'BCBS',     col: 46  },
  { plan: 'BCBS - Minnesota Medicaid Advantage',               family: 'BCBS',     col: 50  },
  { plan: 'BCBS - Anthem (Colorado HMO)',                      family: 'BCBS',     col: 54  },
  { plan: 'BCBS - Anthem (Colorado PPO)',                      family: 'BCBS',     col: 58  },
  { plan: 'BCBS - Anthem (Connecticut)',                       family: 'BCBS',     col: 62  },
  { plan: 'BCBS - Anthem (Indiana)',                           family: 'BCBS',     col: 66  },
  { plan: 'BCBS - Anthem (Maine)',                             family: 'BCBS',     col: 70  },
  { plan: 'BCBS - Anthem (Nevada)',                            family: 'BCBS',     col: 74  },
  { plan: 'BCBS - Anthem (New Hampshire)',                     family: 'BCBS',     col: 78  },
  { plan: 'BCBS - Horizon (New Jersey)',                       family: 'BCBS',     col: 82  },
  { plan: 'BCBS - Independence (Pennsylvania)',                family: 'BCBS',     col: 86  },
  { plan: 'BCBS - Premera (Washington)',                       family: 'BCBS',     col: 90  },
  { plan: 'BCBS - Regence (Washington)',                       family: 'BCBS',     col: 94  },
  { plan: 'BCBS - Regence (Oregon)',                           family: 'BCBS',     col: 98  },
  { plan: 'BCBS - Wellmark (Iowa)',                            family: 'BCBS',     col: 102 },
];

// ── Column layout constants ────────────────────────────────────
// 26 plans × 4 cols = cols 2–105 (A = col 1 label; last SBH = col 105 = DA)
var INSURANCE_LAST_COL   = 105;  // DA — last Wellmark (Iowa) SBH column
var STATE_COL            = 106;  // DB — state name / separator column
var MEDICARE_COL         = 107;  // DC — Medicare Standard
var MEDICARE_REGION1_COL = 108;  // DD — Medicare Region 1
var MEDICARE_REGION2_COL = 109;  // DE — Medicare Region 2
var USER_COLS_START      = 110;  // DF — first of 6 blank user columns
var USER_COLS_END        = 115;  // DK — last blank user column
var TOTAL_COLS           = 115;  // A through DK

var ROWS_PER_STATE = 8;   // state label, date, 5 CPTs, blank separator
var HEADER_ROWS    = 2;   // row 1 = plan names; row 2 = sub-col labels
var SUB_COLS       = ['Alma', 'Headway', 'Grow', 'SBH'];

// Pastel background colors per insurance family
var FAMILY_COLORS = {
  'Aetna':    '#FADBD8',  // light rose
  'Cigna':    '#FDEBD0',  // light orange
  'UHC':      '#D6EAF8',  // light blue
  'Carelon':  '#E8DAEF',  // light purple
  'Ambetter': '#D1F2EB',  // light teal (used for both Ambetter sub-plans)
  'BCBS':     '#FEF9E7',  // light yellow
};

var MEDICARE_COLOR  = '#E9F7EF';  // light green for Medicare section header
var STATE_COL_COLOR = '#EAECEE';  // light gray for state-name separator column

// Bold left-border dividers between main insurance SECTIONS (1-indexed col numbers)
// Cigna | UHC | Carelon | Ambetter | BCBS | State/Medicare
var SECTION_START_COLS = [6, 10, 14, 18, 26, STATE_COL];

// v2 MASTER state-to-row (1-indexed block start; 25 states alphabetically)
var OLD_STATE_TO_ROW = {
  AK: 3,   AZ: 11,  CO: 19,  CT: 27,  DC: 35,  FL: 43,
  HI: 51,  IA: 59,  ID: 67,  KS: 75,  MD: 83,  ME: 91,
  MN: 99,  MT: 107, ND: 115, NE: 123, NH: 131, NM: 139,
  NV: 147, OR: 155, SD: 163, UT: 171, VT: 179, WA: 187,
  WY: 195,
};


// ══════════════════════════════════════════════════════════════
//  MAIN ENTRY POINT
// ══════════════════════════════════════════════════════════════

function buildNewMasterSheet() {
  // 1. Load v2 MASTER data (95 columns covers all 21 v2 plan groups + Medicare)
  Logger.log('Loading v2 MASTER data...');
  var oldSS    = SpreadsheetApp.openById(OLD_MASTER_ID);
  var oldSheet = oldSS.getSheetByName(OLD_MASTER_TAB);
  var oldData  = oldSheet.getRange(1, 1, 210, 95).getValues();

  // 2. Create new spreadsheet
  Logger.log('Creating new Google Spreadsheet...');
  var newSS = SpreadsheetApp.create('Solrei MASTER Rates — v3');
  var sheet = newSS.getActiveSheet();
  sheet.setName('Rates');
  Logger.log('URL: ' + newSS.getUrl());

  // 3. Expand to TOTAL_COLS (new sheets only have 26 columns by default)
  var currentCols = sheet.getMaxColumns();
  if (currentCols < TOTAL_COLS) {
    sheet.insertColumnsAfter(currentCols, TOTAL_COLS - currentCols);
  }

  // 4. Freeze panes and set column widths
  sheet.setFrozenRows(HEADER_ROWS);
  sheet.setFrozenColumns(1);
  sheet.setColumnWidth(1, 90);                          // A: state/CPT label
  for (var c = 2; c <= INSURANCE_LAST_COL; c++) {
    sheet.setColumnWidth(c, 70);                        // insurance data cols
  }
  sheet.setColumnWidth(STATE_COL, 80);                  // DB: state name
  sheet.setColumnWidth(MEDICARE_COL, 80);               // DC: Medicare Standard
  sheet.setColumnWidth(MEDICARE_REGION1_COL, 80);       // DD: Medicare Region 1
  sheet.setColumnWidth(MEDICARE_REGION2_COL, 80);       // DE: Medicare Region 2
  for (var c = USER_COLS_START; c <= USER_COLS_END; c++) {
    sheet.setColumnWidth(c, 90);                        // DF–DK: user columns
  }

  // 5. Build header rows
  Logger.log('Building headers...');
  _buildHeaders(sheet);

  // 6. Build state blocks (blue banners, date rows, CPT rows, migration)
  Logger.log('Building state blocks (this takes several minutes)...');
  _buildStateBlocks(sheet, oldData);

  // 7. Number format on insurance data cells
  var firstDataRow  = HEADER_ROWS + 1;
  var totalDataRows = STATES.length * ROWS_PER_STATE;
  sheet.getRange(firstDataRow, 2, totalDataRows, INSURANCE_LAST_COL - 1)
       .setNumberFormat('[$$-409]#,##0.00;-[$$-409]#,##0.00');

  // 8. Number format on Medicare cells (DC, DD, DE)
  sheet.getRange(firstDataRow, MEDICARE_COL, totalDataRows, 3)
       .setNumberFormat('[$$-409]#,##0.00;-[$$-409]#,##0.00');

  // 9. Conditional formatting — green = max per 4-col insurance group per row
  Logger.log('Applying conditional formatting...');
  _applyConditionalFormatting(sheet, firstDataRow, firstDataRow + totalDataRows - 1);

  Logger.log('Done! ' + newSS.getUrl());
  SpreadsheetApp.getUi().alert(
    '✓  New MASTER v3 sheet created!\n\n' + newSS.getUrl() + '\n\n' +
    'v2 MASTER was NOT modified.\n' +
    '26 plan groups (cols A–DA). Green cells = highest rate per 4-col group.\n' +
    'Medicare rates in cols DC–DE. Blank user cols: DF–DK.'
  );
}


// ══════════════════════════════════════════════════════════════
//  HEADER ROWS (rows 1 & 2)
// ══════════════════════════════════════════════════════════════

function _buildHeaders(sheet) {
  // Row 1: plan name in first cell of each 4-col group; "Medicare" over DC:DE
  var r1 = new Array(TOTAL_COLS).fill('');
  r1[0] = 'State / CPT';
  for (var i = 0; i < PLAN_GROUPS.length; i++) {
    r1[PLAN_GROUPS[i].col - 1] = PLAN_GROUPS[i].plan;
  }
  r1[STATE_COL - 1]       = '';
  r1[MEDICARE_COL - 1]    = 'Medicare';

  // Row 2: sub-col labels (Alma/HW/Grow/SBH per plan); State / Medicare labels
  var r2 = new Array(TOTAL_COLS).fill('');
  for (var i = 0; i < PLAN_GROUPS.length; i++) {
    var base = PLAN_GROUPS[i].col - 1;
    for (var s = 0; s < SUB_COLS.length; s++) { r2[base + s] = SUB_COLS[s]; }
  }
  r2[STATE_COL - 1]            = 'State';
  r2[MEDICARE_COL - 1]         = 'Standard';
  r2[MEDICARE_REGION1_COL - 1] = 'Region';
  r2[MEDICARE_REGION2_COL - 1] = 'Region';

  sheet.getRange(1, 1, 1, TOTAL_COLS).setValues([r1]);
  sheet.getRange(2, 1, 1, TOTAL_COLS).setValues([r2]);
  sheet.setRowHeight(1, 52);
  sheet.setRowHeight(2, 20);

  // ── Label column A1:A2 ───────────────────────────────────────
  sheet.getRange(1, 1, 2, 1)
       .setBackground('#2C3E50').setFontColor('#FFFFFF')
       .setFontWeight('bold').setFontSize(9)
       .setHorizontalAlignment('center').setVerticalAlignment('middle');

  // ── Insurance plan group formatting ─────────────────────────
  for (var i = 0; i < PLAN_GROUPS.length; i++) {
    var pg    = PLAN_GROUPS[i];
    var col   = pg.col;
    var color = FAMILY_COLORS[pg.family] || '#FFFFFF';

    // Merge plan name across 4 cols in row 1
    var r1g = sheet.getRange(1, col, 1, 4);
    r1g.mergeAcross();
    r1g.setValue(pg.plan)
       .setBackground(color).setFontWeight('bold').setFontSize(8)
       .setHorizontalAlignment('center').setVerticalAlignment('middle')
       .setWrap(true).setFontFamily('Arial');

    // Sub-col label row 2
    sheet.getRange(2, col, 1, 4)
         .setBackground(color).setFontWeight('bold').setFontSize(9)
         .setHorizontalAlignment('center').setFontFamily('Arial');

    // SBH label in dark red
    sheet.getRange(2, col + 3).setFontColor('#8B0000').setFontWeight('bold');
  }

  // ── State-name separator column DB ──────────────────────────
  sheet.getRange(1, STATE_COL, 2, 1)
       .setBackground(STATE_COL_COLOR).setFontWeight('bold').setFontSize(9)
       .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sheet.getRange(1, STATE_COL).setValue('');
  sheet.getRange(2, STATE_COL).setValue('State');

  // ── Medicare section DC:DE (3 cols) ─────────────────────────
  var medicareR1 = sheet.getRange(1, MEDICARE_COL, 1, 3);
  medicareR1.mergeAcross();
  medicareR1.setValue('Medicare')
            .setBackground(MEDICARE_COLOR).setFontWeight('bold').setFontSize(10)
            .setHorizontalAlignment('center').setVerticalAlignment('middle');

  sheet.getRange(2, MEDICARE_COL, 1, 3)
       .setBackground(MEDICARE_COLOR).setFontWeight('bold').setFontSize(9)
       .setHorizontalAlignment('center');

  // ── User columns DF–DK (rows 1 & 2) — neutral, no blue ──────
  sheet.getRange(1, USER_COLS_START, 2, USER_COLS_END - USER_COLS_START + 1)
       .setBackground('#FFFFFF').setFontSize(9)
       .setHorizontalAlignment('center');

  // ── Bold dividers between sections ──────────────────────────
  for (var i = 0; i < SECTION_START_COLS.length; i++) {
    var sc = SECTION_START_COLS[i];
    sheet.getRange(1, sc, 2, 1)
         .setBorder(null, true, null, null, null, null,
                    '#333333', SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
  }
}


// ══════════════════════════════════════════════════════════════
//  STATE BLOCKS
// ══════════════════════════════════════════════════════════════

function _buildStateBlocks(sheet, oldData) {
  var startRow = HEADER_ROWS + 1;  // row 3 = first state block

  for (var si = 0; si < STATES.length; si++) {
    var stateCode  = STATES[si][0];
    var stateName  = STATES[si][1];
    var blockStart = startRow + si * ROWS_PER_STATE;
    var stateRow   = blockStart;
    var dateRow    = blockStart + 1;

    // ── Blue state banner (cols A through DE only; user cols stay white) ──
    sheet.setRowHeight(stateRow, 18);

    // Build state row values: state label in A, plan names in group starts, state code in DB
    var stateRowVals = new Array(TOTAL_COLS).fill('');
    stateRowVals[0]             = stateCode + '  —  ' + stateName;
    stateRowVals[STATE_COL - 1] = stateCode;
    for (var pi = 0; pi < PLAN_GROUPS.length; pi++) {
      stateRowVals[PLAN_GROUPS[pi].col - 1] = PLAN_GROUPS[pi].plan;
    }
    sheet.getRange(stateRow, 1, 1, TOTAL_COLS).setValues([stateRowVals]);

    // Blue banner on cols 1 through DE (MEDICARE_REGION2_COL)
    sheet.getRange(stateRow, 1, 1, MEDICARE_REGION2_COL)
         .setBackground('#2980B9').setFontColor('#FFFFFF')
         .setFontWeight('bold').setFontSize(8);
    sheet.getRange(stateRow, 1).setFontSize(9).setHorizontalAlignment('left');
    sheet.getRange(stateRow, STATE_COL)
         .setBackground('#1A5276')
         .setHorizontalAlignment('center').setFontSize(8);
    // User cols: white, default text
    sheet.getRange(stateRow, USER_COLS_START, 1, USER_COLS_END - USER_COLS_START + 1)
         .setBackground('#FFFFFF').setFontColor('#000000').setFontWeight('normal');

    // Merge plan name across 4 cols in the state row (for each plan group)
    for (var pi = 0; pi < PLAN_GROUPS.length; pi++) {
      var planRange = sheet.getRange(stateRow, PLAN_GROUPS[pi].col, 1, 4);
      planRange.mergeAcross();
      planRange.setHorizontalAlignment('center').setFontSize(7).setFontWeight('bold');
    }

    // Bold section dividers in the state row
    for (var i = 0; i < SECTION_START_COLS.length; i++) {
      sheet.getRange(stateRow, SECTION_START_COLS[i])
           .setBorder(null, true, null, null, null, null,
                      '#FFFFFF', SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
    }

    // ── Date row ──────────────────────────────────────────────
    sheet.setRowHeight(dateRow, 16);
    // Light blue only on cols 1 through DE
    sheet.getRange(dateRow, 1, 1, MEDICARE_REGION2_COL)
         .setBackground('#EBF5FB').setFontSize(8).setFontStyle('italic');
    // User cols: white
    sheet.getRange(dateRow, USER_COLS_START, 1, USER_COLS_END - USER_COLS_START + 1)
         .setBackground('#FFFFFF').setFontStyle('normal');

    sheet.getRange(dateRow, 1).setValue('Date').setHorizontalAlignment('right');
    sheet.getRange(dateRow, STATE_COL)
         .setValue(stateCode).setBackground(STATE_COL_COLOR)
         .setHorizontalAlignment('center').setFontWeight('bold').setFontStyle('normal');
    sheet.getRange(dateRow, MEDICARE_COL, 1, 3).setBackground(MEDICARE_COLOR);

    // Bold dividers in date row
    for (var i = 0; i < SECTION_START_COLS.length; i++) {
      sheet.getRange(dateRow, SECTION_START_COLS[i])
           .setBorder(null, true, null, null, null, null,
                      '#333333', SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
    }

    // ── CPT code rows ─────────────────────────────────────────
    for (var ci = 0; ci < CPT_CODES.length; ci++) {
      var cptRow = blockStart + 2 + ci;
      sheet.setRowHeight(cptRow, 18);

      // CPT label in col A
      sheet.getRange(cptRow, 1)
           .setValue(CPT_CODES[ci]).setHorizontalAlignment('center').setFontSize(9);

      // State code in DB
      sheet.getRange(cptRow, STATE_COL)
           .setValue(stateCode).setBackground(STATE_COL_COLOR)
           .setHorizontalAlignment('center').setFontSize(8).setFontWeight('bold');

      // Alternate row shading on insurance cols only (not user cols)
      if (ci % 2 === 1) {
        sheet.getRange(cptRow, 2, 1, INSURANCE_LAST_COL - 1).setBackground('#F4F8FC');
      }

      // Medicare cols DC:DE light green background
      sheet.getRange(cptRow, MEDICARE_COL, 1, 3).setBackground(MEDICARE_COLOR);

      // Bold dividers in CPT rows
      for (var i = 0; i < SECTION_START_COLS.length; i++) {
        sheet.getRange(cptRow, SECTION_START_COLS[i])
             .setBorder(null, true, null, null, null, null,
                        '#333333', SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
      }
    }

    // ── Blank separator row (row 7 of block) ─────────────────
    sheet.setRowHeight(blockStart + 7, 5);

    // ── Migrate data from v2 MASTER ───────────────────────────
    if (OLD_STATE_TO_ROW[stateCode] !== undefined) {
      _migrateStateData(sheet, oldData, stateCode,
                        OLD_STATE_TO_ROW[stateCode], blockStart, dateRow);
    }
  }
}


// ══════════════════════════════════════════════════════════════
//  DATA MIGRATION — v2 MASTER → v3 columns
// ══════════════════════════════════════════════════════════════

function _migrateStateData(sheet, oldData, stateCode, oldStateRow, newBlockStart, newDateRow) {
  /**
   * oldStateRow: 1-indexed label row in v2 MASTER
   * oldData is 0-indexed:
   *   oldData[oldStateRow]         = date row  (0-indexed = 1-indexed stateRow + 1 - 1 = stateRow)
   *   oldData[oldStateRow + N - 1] = CPT row for CPT_OFFSETS N
   *
   * v2 column positions (source):
   *   Aetna 2–5 | Cigna 6–9 | UHC 10–13 | Carelon 14–17 | Ambetter 18–21
   *   FL Blue 22–25 | FL Blue MA 26–29 | BCBS AZ 30–33 | BCBS MA 34–37 | BCBS MN 38–41
   *   Anthem CO 42–45 | Anthem CT 46–49 | Anthem IN 50–53 | Anthem ME 54–57
   *   Anthem NV 58–61 | Anthem NH 62–65 | Horizon NJ 66–69 | Independence PA 70–73
   *   Premera WA 74–77 | Regence WA 78–81 | Wellmark 82–85
   *   State 86 | Medicare Standard 87 | Medicare Region1 88 | Medicare Region2 89
   *
   * v3 column positions (destination):
   *   Aetna 2–5 | Cigna 6–9 | UHC 10–13 | Carelon 14–17 | Ambetter 18–21
   *   Ambetter WA 22–25 (NEW) | FL Blue 26–29 | FL Blue MA 30–33 | BCBS AZ 34–37
   *   BCBS MA 38–41 | BCBS MN 42–45 | MN Medicaid 46–49 (NEW) | MN MA 50–53 (NEW)
   *   Anthem CO HMO 54–57 | Anthem CO PPO 58–61 (NEW) | Anthem CT 62–65
   *   Anthem IN 66–69 | Anthem ME 70–73 | Anthem NV 74–77 | Anthem NH 78–81
   *   Horizon NJ 82–85 | Independence PA 86–89 | Premera WA 90–93
   *   Regence WA 94–97 | Regence OR 98–101 (NEW) | Wellmark Iowa 102–105
   *   State 106 | Medicare Standard 107 | Medicare Region1 108 | Medicare Region2 109
   */

  // [oldCol_1indexed, newCol_1indexed]
  // NEW plans (Ambetter WA, MN Medicaid, MN MA, CO PPO, Regence OR) have no v2 source.
  var universalMap = [
    [2,  2 ], [3,  3 ], [4,  4 ], [5,  5 ],   // Aetna (unchanged)
    [6,  6 ], [7,  7 ], [8,  8 ], [9,  9 ],   // Cigna (unchanged)
    [10, 10], [11, 11], [12, 12], [13, 13],   // UHC (unchanged)
    [14, 14], [15, 15], [16, 16], [17, 17],   // Carelon (unchanged)
    [18, 18], [19, 19], [20, 20], [21, 21],   // Ambetter (unchanged)
    // Ambetter WA cols 22–25: NEW
    [22, 26], [23, 27], [24, 28], [25, 29],   // FL Blue (22-25 → 26-29)
    [26, 30], [27, 31], [28, 32], [29, 33],   // FL Blue MA (26-29 → 30-33)
    [30, 34], [31, 35], [32, 36], [33, 37],   // BCBS AZ (30-33 → 34-37)
    [34, 38], [35, 39], [36, 40], [37, 41],   // BCBS MA (34-37 → 38-41)
    [38, 42], [39, 43], [40, 44], [41, 45],   // BCBS MN (38-41 → 42-45)
    // MN Medicaid 46–49: NEW
    // MN Medicaid Advantage 50–53: NEW
    [42, 54], [43, 55], [44, 56], [45, 57],   // Anthem CO → CO HMO (42-45 → 54-57)
    // Anthem CO PPO 58–61: NEW
    [46, 62], [47, 63], [48, 64], [49, 65],   // Anthem CT (46-49 → 62-65)
    [50, 66], [51, 67], [52, 68], [53, 69],   // Anthem IN (50-53 → 66-69)
    [54, 70], [55, 71], [56, 72], [57, 73],   // Anthem ME (54-57 → 70-73)
    [58, 74], [59, 75], [60, 76], [61, 77],   // Anthem NV (58-61 → 74-77)
    [62, 78], [63, 79], [64, 80], [65, 81],   // Anthem NH (62-65 → 78-81)
    [66, 82], [67, 83], [68, 84], [69, 85],   // Horizon NJ (66-69 → 82-85)
    [70, 86], [71, 87], [72, 88], [73, 89],   // Independence PA (70-73 → 86-89)
    [74, 90], [75, 91], [76, 92], [77, 93],   // Premera WA (74-77 → 90-93)
    [78, 94], [79, 95], [80, 96], [81, 97],   // Regence WA (78-81 → 94-97)
    // Regence OR 98–101: NEW
    [82, 102], [83, 103], [84, 104], [85, 105], // Wellmark Iowa (82-85 → 102-105)
    [87, 107], [88, 108], [89, 109],            // Medicare (87→107, 88→108, 89→109)
    [86, 106],                                   // State name (86→106)
  ];

  // ── Migrate date row ─────────────────────────────────────────
  // oldStateRow (1-indexed label) → oldData[oldStateRow] is the date row (0-indexed)
  var oldDateIdx = oldStateRow;
  for (var m = 0; m < universalMap.length; m++) {
    var oc = universalMap[m][0] - 1;  // 0-indexed old col
    var nc = universalMap[m][1];      // 1-indexed new col
    var dv = oldData[oldDateIdx][oc];
    if (dv && String(dv).trim() !== '') {
      sheet.getRange(newDateRow, nc).setValue(dv);
    }
  }

  // ── Migrate CPT rows ─────────────────────────────────────────
  for (var ci = 0; ci < CPT_CODES.length; ci++) {
    var cpt       = CPT_CODES[ci];
    var oldCptIdx = oldStateRow + CPT_OFFSETS[cpt] - 1;  // 0-indexed
    var newCptRow = newBlockStart + 2 + ci;               // 1-indexed

    for (var m = 0; m < universalMap.length; m++) {
      var oc  = universalMap[m][0] - 1;
      var nc  = universalMap[m][1];
      var val = oldData[oldCptIdx][oc];
      if (typeof val === 'number' && !isNaN(val) && val > 0) {
        sheet.getRange(newCptRow, nc).setValue(val);
      }
    }
  }
}


// ══════════════════════════════════════════════════════════════
//  CONDITIONAL FORMATTING — green fill = max per 4-col group
//  (insurance cols only, B through DA = cols 2–105)
// ══════════════════════════════════════════════════════════════

function _applyConditionalFormatting(sheet, firstDataRow, lastDataRow) {
  var anchor  = 'B' + firstDataRow;
  var formula = '=AND(ISNUMBER(' + anchor + '),' + anchor +
                '=MAX(OFFSET(' + anchor + ',0,-MOD(COLUMN(' + anchor + ')-2,4),1,4)))';

  var dataRange = sheet.getRange(firstDataRow, 2,
                                 lastDataRow - firstDataRow + 1,
                                 INSURANCE_LAST_COL - 1);
  var rule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied(formula)
    .setBackground('#00B050')
    .setFontColor('#FFFFFF')
    .setRanges([dataRange])
    .build();

  var rules = sheet.getConditionalFormatRules();
  rules.push(rule);
  sheet.setConditionalFormatRules(rules);
}


// ══════════════════════════════════════════════════════════════
//  UTILITY — reapply conditional formatting to existing sheet
// ══════════════════════════════════════════════════════════════

function reapplyConditionalFormatting() {
  var sheet        = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Rates');
  var firstDataRow = HEADER_ROWS + 1;
  var lastDataRow  = firstDataRow + STATES.length * ROWS_PER_STATE - 1;
  sheet.clearConditionalFormatRules();
  _applyConditionalFormatting(sheet, firstDataRow, lastDataRow);
  SpreadsheetApp.getActiveSpreadsheet().toast('Conditional formatting reapplied.', 'Done', 5);
}


// ══════════════════════════════════════════════════════════════
//  MENU
// ══════════════════════════════════════════════════════════════

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Solrei MASTER Builder')
    .addItem('Build New MASTER Sheet (v3)', 'buildNewMasterSheet')
    .addSeparator()
    .addItem('Reapply Conditional Formatting', 'reapplyConditionalFormatting')
    .addToUi();
}
