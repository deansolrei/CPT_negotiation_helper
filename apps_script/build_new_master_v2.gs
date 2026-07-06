/**
 * Solrei CPT Dashboard — New MASTER Google Sheet Builder (v2)
 *
 * Structure:
 *  Cols A–CG  (1–85):   21 insurance plan groups × 4 sub-cols (Alma | Headway | Grow | SBH)
 *  Col  CH    (86):     State name — repeated on every row for easy reading at far right
 *  Col  CI    (87):     Medicare — Standard rate (migrated from old MASTER col X = 24)
 *  Col  CJ    (88):     Medicare — City / locality variation (migrated from old MASTER col Y = 25)
 *  Cols CK–CP (89–94):  6 blank user columns for additional content
 *
 * Plan order: Aetna → Cigna → UHC → Carelon → Ambetter → BCBS (16 sub-plans)
 * Bold vertical borders between main insurance sections (Cigna, UHC, Carelon, Ambetter, BCBS, Medicare)
 * Each state's blue header row shows plan names centered over each 4-col group
 * Green conditional formatting = highest rate per 4-col insurance group per row
 *   (conditional formatting covers insurance cols only, not Medicare cols)
 *
 * HOW TO USE:
 * 1. Open any Google Sheet → Extensions → Apps Script
 * 2. Paste this entire script, Save (Ctrl+S)
 * 3. Run → buildNewMasterSheet
 * 4. Grant permissions when prompted (one-time)
 * 5. URL appears in View → Logs and in an alert dialog when done
 *
 * Old MASTER is NOT modified. Estimated runtime: 5–8 minutes.
 */

// ── Source: old MASTER to migrate data FROM ───────────────────
var OLD_MASTER_ID  = '1QyfSpVlAba_epE1eehN5wlU1543AGWEpIzmsGPNlgXE';
var OLD_MASTER_TAB = 'Rates';

// ── CPT codes and row offsets within each state block ─────────
// Block layout: row 0 = state label, row 1 = date, rows 2–6 = CPTs, row 7 = blank gap
var CPT_CODES   = ['99214', '99215', '90833', '90836', '90838'];
var CPT_OFFSETS = { '99214': 2, '99215': 3, '90833': 4, '90836': 5, '90838': 6 };

// ── States (alphabetical, 25 total) ───────────────────────────
// VT / ME / KS kept in MASTER sheet even though removed from the dashboard tool
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

// ── Insurance plan groups ─────────────────────────────────────
// col: 1-indexed starting column of the 4-column group
// Sub-columns: col=Alma, col+1=Headway, col+2=Grow Therapy, col+3=SBH
var PLAN_GROUPS = [
  // ── Aetna ─────────────────────────────────────────────────
  { plan: 'Aetna',                                             family: 'Aetna',    col: 2  },
  // ── Cigna ─────────────────────────────────────────────────
  { plan: 'Cigna',                                             family: 'Cigna',    col: 6  },
  // ── UHC / Oscar / Optum ───────────────────────────────────
  { plan: 'UHC / Oscar / Optum',                               family: 'UHC',      col: 10 },
  // ── Carelon ───────────────────────────────────────────────
  { plan: 'Carelon Behavioral Health',                         family: 'Carelon',  col: 14 },
  // ── Ambetter ──────────────────────────────────────────────
  { plan: 'Ambetter',                                          family: 'Ambetter', col: 18 },
  // ── BCBS / Anthem / Blue family ───────────────────────────
  { plan: 'BCBS - Florida Blue',                               family: 'BCBS',     col: 22 },
  { plan: 'BCBS - Florida Blue Medicare Advantage',            family: 'BCBS',     col: 26 },
  { plan: 'BCBS - of Arizona',                                 family: 'BCBS',     col: 30 },
  { plan: 'BCBS - of Massachusetts',                           family: 'BCBS',     col: 34 },
  { plan: 'BCBS - of Minnesota',                               family: 'BCBS',     col: 38 },
  { plan: 'BCBS - Anthem (Colorado)',                          family: 'BCBS',     col: 42 },
  { plan: 'BCBS - Anthem (Connecticut)',                       family: 'BCBS',     col: 46 },
  { plan: 'BCBS - Anthem (Indiana)',                           family: 'BCBS',     col: 50 },
  { plan: 'BCBS - Anthem (Maine)',                             family: 'BCBS',     col: 54 },
  { plan: 'BCBS - Anthem (Nevada)',                            family: 'BCBS',     col: 58 },
  { plan: 'BCBS - Anthem (New Hampshire)',                     family: 'BCBS',     col: 62 },
  { plan: 'BCBS - Horizon (New Jersey)',                       family: 'BCBS',     col: 66 },
  { plan: 'BCBS - Independence (Pennsylvania)',                family: 'BCBS',     col: 70 },
  { plan: 'BCBS - Premera (Washington)',                       family: 'BCBS',     col: 74 },
  { plan: 'BCBS - Regence (Washington)',                       family: 'BCBS',     col: 78 },
  { plan: 'BCBS - Wellmark',                                   family: 'BCBS',     col: 82 },
];

// ── Column layout constants ────────────────────────────────────
var INSURANCE_LAST_COL   = 85;   // CG — last BCBS-Wellmark SBH column
var STATE_COL            = 86;   // CH — state name / separator column
var MEDICARE_COL         = 87;   // CI — Medicare Standard  (old MASTER col Y = 25)
var MEDICARE_REGION1_COL = 88;   // CJ — Medicare Region    (old MASTER col Z = 26)
var MEDICARE_REGION2_COL = 89;   // CK — Medicare Region    (old MASTER col AA = 27)
var USER_COLS_START      = 90;   // CL — first of 6 blank user columns
var USER_COLS_END        = 95;   // CQ — last blank user column
var TOTAL_COLS           = 95;   // A through CQ

var ROWS_PER_STATE = 8;   // state label, date, 5 CPTs, blank separator
var HEADER_ROWS    = 2;   // row 1 = plan names / section names; row 2 = sub-col labels
var SUB_COLS       = ['Alma', 'Headway', 'Grow', 'SBH'];

// Pastel background colors per insurance family
var FAMILY_COLORS = {
  'Aetna':    '#FADBD8',  // light rose
  'Cigna':    '#FDEBD0',  // light orange
  'UHC':      '#D6EAF8',  // light blue
  'Carelon':  '#E8DAEF',  // light purple
  'Ambetter': '#D1F2EB',  // light teal
  'BCBS':     '#FEF9E7',  // light yellow
};

var MEDICARE_COLOR = '#E9F7EF';  // light green for Medicare section header
var STATE_COL_COLOR = '#EAECEE'; // light gray for state-name separator column

// Bold left-border dividers between insurance SECTIONS (1-indexed col numbers)
// Also includes STATE_COL to visually separate the Medicare block
var SECTION_START_COLS = [6, 10, 14, 18, 22, STATE_COL];

// Old MASTER state-to-row (1-indexed; includes KS/ME/VT from v5)
var OLD_STATE_TO_ROW = {
  AK: 3,   AZ: 11,  CO: 19,  FL: 27,  HI: 35,  ID: 43,  IA: 51,  MD: 59,
  MN: 67,  MT: 75,  NE: 83,  NV: 91,  NM: 99,  ND: 107, OR: 115, SD: 123,
  WA: 131, DC: 139, WY: 147, KS: 155, NH: 163, ME: 171, VT: 179, CT: 187, UT: 195,
};


// ══════════════════════════════════════════════════════════════
//  MAIN ENTRY POINT
// ══════════════════════════════════════════════════════════════

function buildNewMasterSheet() {
  // 1. Load old MASTER data — read 30 cols to capture Medicare cols X (24) & Y (25)
  Logger.log('Loading old MASTER data...');
  var oldSS    = SpreadsheetApp.openById(OLD_MASTER_ID);
  var oldSheet = oldSS.getSheetByName(OLD_MASTER_TAB);
  var oldData  = oldSheet.getRange(1, 1, 210, 30).getValues();

  // 2. Create new spreadsheet
  Logger.log('Creating new Google Spreadsheet...');
  var newSS = SpreadsheetApp.create('Solrei MASTER Rates — v2');
  var sheet = newSS.getActiveSheet();
  sheet.setName('Rates');
  Logger.log('URL: ' + newSS.getUrl());

  // 3. Expand to TOTAL_COLS columns (new sheets only have 26 by default)
  var currentCols = sheet.getMaxColumns();
  if (currentCols < TOTAL_COLS) {
    sheet.insertColumnsAfter(currentCols, TOTAL_COLS - currentCols);
  }

  // 4. Freeze panes and set column widths
  sheet.setFrozenRows(HEADER_ROWS);
  sheet.setFrozenColumns(1);
  sheet.setColumnWidth(1, 90);                        // A: state/CPT label
  for (var c = 2; c <= INSURANCE_LAST_COL; c++) {
    sheet.setColumnWidth(c, 70);                      // insurance data cols
  }
  sheet.setColumnWidth(STATE_COL, 80);                // CH: state name
  sheet.setColumnWidth(MEDICARE_COL, 80);             // CI: Medicare Standard
  sheet.setColumnWidth(MEDICARE_REGION1_COL, 80);     // CJ: Medicare Region
  sheet.setColumnWidth(MEDICARE_REGION2_COL, 80);     // CK: Medicare Region
  for (var c = USER_COLS_START; c <= USER_COLS_END; c++) {
    sheet.setColumnWidth(c, 90);                      // CK–CP: user columns
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

  // 8. Number format on Medicare cells (CI, CJ, CK)
  sheet.getRange(firstDataRow, MEDICARE_COL, totalDataRows, 3)
       .setNumberFormat('[$$-409]#,##0.00;-[$$-409]#,##0.00');

  // 9. Conditional formatting — green = max per 4-col insurance group per row
  //    (insurance cols only, B through CG)
  Logger.log('Applying conditional formatting...');
  _applyConditionalFormatting(sheet, firstDataRow, firstDataRow + totalDataRows - 1);

  Logger.log('Done! ' + newSS.getUrl());
  SpreadsheetApp.getUi().alert(
    '✓  New MASTER sheet created!\n\n' + newSS.getUrl() + '\n\n' +
    'Old MASTER was NOT modified.\n' +
    'Green cells = highest rate within each 4-column plan group.\n' +
    'Medicare rates are in cols CI–CJ. Blank user cols: CK–CP.'
  );
}


// ══════════════════════════════════════════════════════════════
//  HEADER ROWS (rows 1 & 2)
// ══════════════════════════════════════════════════════════════

function _buildHeaders(sheet) {
  // Row 1: plan name in first cell of each 4-col group; section titles for Medicare/user area
  var r1 = new Array(TOTAL_COLS).fill('');
  r1[0] = 'State / CPT';
  for (var i = 0; i < PLAN_GROUPS.length; i++) {
    r1[PLAN_GROUPS[i].col - 1] = PLAN_GROUPS[i].plan;
  }
  r1[STATE_COL - 1]         = '';           // CH — blank in row 1 (row 2 label is enough)
  r1[MEDICARE_COL - 1]      = 'Medicare';   // CI — merged over CI:CJ in formatting below
  r1[USER_COLS_START - 1]   = '';           // CK — user fills in

  // Row 2: sub-col labels (Alma/HW/Grow/SBH per plan); Medicare and state labels
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

  // ── State-name separator column CH ──────────────────────────
  sheet.getRange(1, STATE_COL, 2, 1)
       .setBackground(STATE_COL_COLOR).setFontWeight('bold').setFontSize(9)
       .setHorizontalAlignment('center').setVerticalAlignment('middle');
  sheet.getRange(1, STATE_COL).setValue('');
  sheet.getRange(2, STATE_COL).setValue('State');

  // ── Medicare section CI:CK (3 cols) ─────────────────────────
  // Merge "Medicare" header across CI:CK in row 1
  var medicareR1 = sheet.getRange(1, MEDICARE_COL, 1, 3);
  medicareR1.mergeAcross();
  medicareR1.setValue('Medicare')
            .setBackground(MEDICARE_COLOR).setFontWeight('bold').setFontSize(10)
            .setHorizontalAlignment('center').setVerticalAlignment('middle');

  sheet.getRange(2, MEDICARE_COL, 1, 3)
       .setBackground(MEDICARE_COLOR).setFontWeight('bold').setFontSize(9)
       .setHorizontalAlignment('center');

  // ── User columns CK–CP (rows 1 & 2) ─────────────────────────
  sheet.getRange(1, USER_COLS_START, 2, USER_COLS_END - USER_COLS_START + 1)
       .setBackground('#F8F9FA').setFontSize(9)
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

    // ── Blue state banner ─────────────────────────────────────
    sheet.setRowHeight(stateRow, 18);

    // Build state row values: state name in A, plan names in group starts, state code in CH
    var stateRowVals = new Array(TOTAL_COLS).fill('');
    stateRowVals[0]              = stateCode + '  —  ' + stateName;
    stateRowVals[STATE_COL - 1]  = stateCode;
    for (var pi = 0; pi < PLAN_GROUPS.length; pi++) {
      stateRowVals[PLAN_GROUPS[pi].col - 1] = PLAN_GROUPS[pi].plan;
    }
    sheet.getRange(stateRow, 1, 1, TOTAL_COLS).setValues([stateRowVals]);

    // Style entire state row
    sheet.getRange(stateRow, 1, 1, TOTAL_COLS)
         .setBackground('#2980B9').setFontColor('#FFFFFF')
         .setFontWeight('bold').setFontSize(8);
    sheet.getRange(stateRow, 1).setFontSize(9).setHorizontalAlignment('left');
    sheet.getRange(stateRow, STATE_COL)
         .setBackground('#1A5276')  // slightly darker for the state-name col
         .setHorizontalAlignment('center').setFontSize(8);

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
    sheet.getRange(dateRow, 1, 1, TOTAL_COLS)
         .setBackground('#EBF5FB').setFontSize(8).setFontStyle('italic');
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

      // State code in CH
      sheet.getRange(cptRow, STATE_COL)
           .setValue(stateCode).setBackground(STATE_COL_COLOR)
           .setHorizontalAlignment('center').setFontSize(8).setFontWeight('bold');

      // Alternate row shading on insurance cols
      if (ci % 2 === 1) {
        sheet.getRange(cptRow, 2, 1, INSURANCE_LAST_COL - 1).setBackground('#F4F8FC');
      }

      // Medicare cols CI:CK light green background
      sheet.getRange(cptRow, MEDICARE_COL, 1, 3).setBackground(MEDICARE_COLOR);

      // Bold dividers in CPT rows
      for (var i = 0; i < SECTION_START_COLS.length; i++) {
        sheet.getRange(cptRow, SECTION_START_COLS[i])
             .setBorder(null, true, null, null, null, null,
                        '#333333', SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
      }
    }

    // ── Blank separator (row 7 of block) ─────────────────────
    sheet.setRowHeight(blockStart + 7, 5);

    // ── Migrate data from old MASTER ──────────────────────────
    if (OLD_STATE_TO_ROW[stateCode] !== undefined) {
      _migrateStateData(sheet, oldData, stateCode,
                        OLD_STATE_TO_ROW[stateCode], blockStart, dateRow);
    }
  }
}


// ══════════════════════════════════════════════════════════════
//  DATA MIGRATION — old MASTER → new columns
// ══════════════════════════════════════════════════════════════

function _migrateStateData(sheet, oldData, stateCode, oldStateRow, newBlockStart, newDateRow) {
  /**
   * oldStateRow: 1-indexed label row in old MASTER
   * oldData is 0-indexed:
   *   oldData[oldStateRow]       = date row
   *   oldData[oldStateRow + N-1] = CPT row for CPT_OFFSET N
   *
   * New column positions:
   *   Aetna : 2–5    Cigna : 6–9    UHC : 10–13   Carelon : 14–17
   *   Ambetter: 18–21
   *   BCBS FL Blue: 22–25    FL Blue MA: 26–29   BCBS AZ: 30–33
   *   BCBS MA: 34–37         BCBS MN: 38–41
   *   Anthem CO: 42–45       Anthem CT: 46–49    Anthem IN: 50–53
   *   Anthem ME: 54–57       Anthem NV: 58–61    Anthem NH: 62–65
   *   Horizon NJ: 66–69      Independence PA: 70–73
   *   Premera WA: 74–77      Regence WA: 78–81   Wellmark: 82–85
   *   State col: 86  Medicare: 87   Medicare City: 88
   */

  // Universal mappings — same for every state [oldCol_1indexed, newCol_1indexed]
  var universalMap = [
    [6,  2],   // Aetna Alma
    [7,  3],   // Aetna Headway
    [8,  4],   // Aetna Grow
    [9,  5],   // Aetna SBH
    [10, 6],   // Cigna Alma
    [11, 7],   // Cigna Headway
    [12, 8],   // Cigna Grow
    [13, 9],   // Cigna SBH
    [2,  10],  // UHC Alma
    [3,  11],  // UHC Headway
    [4,  12],  // UHC Grow
    [5,  13],  // UHC SBH
    [25, 87],  // Medicare Standard  (old col Y = 25) → CI
    [26, 88],  // Medicare Region    (old col Z = 26) → CJ
    [27, 89],  // Medicare Region    (old col AA= 27) → CK
  ];

  // State-specific mappings (old col → new col)
  var stateExtraMap = {
    'AK': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 67],  // Horizon NJ Headway
      [19, 71],  // Independence PA Headway
    ],
    'AZ': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 31],  // BCBS AZ Headway
    ],
    'CO': [
      [14, 42],  // Anthem CO Alma
      [18, 43],  // Anthem CO Headway (old col = HMO; PPO skipped to avoid conflict)
    ],
    'CT': [
      [14, 46],  // Anthem CT Alma
    ],
    'FL': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [19, 23],  // Florida Blue Headway
      [20, 27],  // Florida Blue Medicare Advantage Headway
      [21, 67],  // Horizon NJ Headway
      [22, 71],  // Independence PA Headway
      [23, 51],  // Anthem Indiana Headway
    ],
    'IA': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
    ],
    'MN': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 39],  // BCBS MN Headway
    ],
    'NH': [
      [14, 62],  // Anthem NH Alma
      [18, 75],  // Premera WA Headway
    ],
    'NM': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
    ],
    'NV': [
      [14, 58],  // Anthem NV Alma
    ],
    'OR': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      // Old col 18 = Regence OR — not in new plan list; skipped
    ],
    'WA': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 35],  // BCBS MA Headway (WA only)
      [19, 67],  // Horizon NJ Headway
      [20, 71],  // Independence PA Headway
      [21, 79],  // Regence WA Headway
      [22, 75],  // Premera WA Headway
    ],
  };

  var colMap = universalMap.slice();
  if (stateExtraMap[stateCode]) {
    colMap = colMap.concat(stateExtraMap[stateCode]);
  }

  // ── Migrate date row ─────────────────────────────────────────
  var oldDateIdx = oldStateRow; // 0-indexed in oldData
  for (var m = 0; m < colMap.length; m++) {
    var oc = colMap[m][0] - 1;  // 0-indexed old col
    var nc = colMap[m][1];      // 1-indexed new col
    var dv = oldData[oldDateIdx][oc];
    if (dv && String(dv).trim() !== '') {
      sheet.getRange(newDateRow, nc).setValue(dv);
    }
  }

  // ── Migrate CPT rows ─────────────────────────────────────────
  for (var ci = 0; ci < CPT_CODES.length; ci++) {
    var cpt       = CPT_CODES[ci];
    var oldCptIdx = oldStateRow + CPT_OFFSETS[cpt] - 1; // 0-indexed
    var newCptRow = newBlockStart + 2 + ci;              // 1-indexed

    for (var m = 0; m < colMap.length; m++) {
      var oc  = colMap[m][0] - 1;
      var nc  = colMap[m][1];
      var val = oldData[oldCptIdx][oc];
      if (typeof val === 'number' && !isNaN(val) && val > 0) {
        sheet.getRange(newCptRow, nc).setValue(val);
      }
    }
  }
}


// ══════════════════════════════════════════════════════════════
//  CONDITIONAL FORMATTING — green fill = max per 4-col group
//  (insurance cols B–CG only; Medicare and user cols excluded)
// ══════════════════════════════════════════════════════════════

function _applyConditionalFormatting(sheet, firstDataRow, lastDataRow) {
  var anchor  = 'B' + firstDataRow;
  var formula = '=AND(ISNUMBER(' + anchor + '),' + anchor +
                '=MAX(OFFSET(' + anchor + ',0,-MOD(COLUMN(' + anchor + ')-2,4),1,4)))';

  // Apply only to insurance data cols (B through CG = cols 2 through 85)
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
    .addItem('Build New MASTER Sheet', 'buildNewMasterSheet')
    .addSeparator()
    .addItem('Reapply Conditional Formatting', 'reapplyConditionalFormatting')
    .addToUi();
}
