/**
 * Solrei CPT Dashboard — New MASTER Google Sheet Builder (v1)
 *
 * Creates a brand-new Google Spreadsheet with redesigned structure:
 *  - 25 insurance plan groups × 4 sub-columns: Alma | Headway | Grow | SBH
 *  - Plans grouped by insurer family (Optum → Aetna → Cigna → Carelon → Wellmark → BCBS)
 *  - 25 state blocks (AK–WY alphabetical, including VT/ME/KS), each with:
 *      Row 0: state label row (blue header)
 *      Row 1: date row
 *      Rows 2-6: CPT codes (99214, 99215, 90833, 90836, 90838)
 *      Row 7: blank separator
 *  - Migrates existing data from old MASTER where column mapping is known
 *  - Applies conditional formatting: green fill = highest value per 4-col group per row
 *
 * HOW TO USE:
 * 1. Open any Google Sheet → Extensions → Apps Script
 * 2. Paste this entire script, Save (Ctrl+S)
 * 3. Run → buildNewMasterSheet
 * 4. Grant permissions when prompted (one-time)
 * 5. Check View → Logs for the new sheet URL
 *    (or an alert dialog will show the URL when it's done)
 *
 * The OLD MASTER IS NOT MODIFIED. This is entirely non-destructive.
 * Estimated runtime: 2–4 minutes (migration + formatting).
 */

// ── Old MASTER to migrate data FROM ───────────────────────────
var OLD_MASTER_ID  = '1QyfSpVlAba_epE1eehN5wlU1543AGWEpIzmsGPNlgXE';
var OLD_MASTER_TAB = 'Rates';

// ── CPT codes and their row offsets within each state block ───
// Offset 0 = state label row, 1 = date row, 2-6 = CPT rows
var CPT_CODES   = ['99214', '99215', '90833', '90836', '90838'];
var CPT_OFFSETS = { '99214': 2, '99215': 3, '90833': 4, '90836': 5, '90838': 6 };

// ── States in new MASTER (alphabetical, 25 total) ─────────────
// Format: [abbrev, display name]
// VT, ME, KS are included even though removed from the dashboard tool
var STATES = [
  ['AK', 'Alaska'],        ['AZ', 'Arizona'],       ['CO', 'Colorado'],
  ['CT', 'Connecticut'],   ['DC', 'Washington DC'],  ['FL', 'Florida'],
  ['HI', 'Hawaii'],        ['IA', 'Iowa'],           ['ID', 'Idaho'],
  ['KS', 'Kansas'],        ['MD', 'Maryland'],       ['ME', 'Maine'],
  ['MN', 'Minnesota'],     ['MT', 'Montana'],        ['ND', 'North Dakota'],
  ['NE', 'Nebraska'],      ['NH', 'New Hampshire'],  ['NM', 'New Mexico'],
  ['NV', 'Nevada'],        ['OR', 'Oregon'],         ['SD', 'South Dakota'],
  ['UT', 'Utah'],          ['VT', 'Vermont'],        ['WA', 'Washington'],
  ['WY', 'Wyoming'],
];

// ── Insurance plan groups ─────────────────────────────────────
// col: 1-indexed starting column for the 4-column group
// Sub-columns within each group: +0=Alma, +1=Headway, +2=Grow Therapy, +3=SBH
var PLAN_GROUPS = [
  // ── Optum family (UHC / Oscar / Oxford / Surest) ─────────
  { plan: 'UHC / Oscar / Optum',                               family: 'Optum',    col: 2  },
  { plan: 'Oxford Health Plans (UHC)',                         family: 'Optum',    col: 6  },
  { plan: 'Oscar Health (UHC)',                                family: 'Optum',    col: 10 },
  { plan: 'Surest (Optum)',                                    family: 'Optum',    col: 14 },
  // ── Aetna ────────────────────────────────────────────────
  { plan: 'Aetna',                                             family: 'Aetna',   col: 18 },
  // ── Cigna ────────────────────────────────────────────────
  { plan: 'Cigna',                                             family: 'Cigna',   col: 22 },
  // ── Carelon ──────────────────────────────────────────────
  { plan: 'Carelon Behavioral Health',                         family: 'Carelon', col: 26 },
  // ── Wellmark (Iowa + bordering counties) ─────────────────
  { plan: 'Wellmark',                                          family: 'Wellmark',col: 30 },
  // ── BCBS / Anthem family ─────────────────────────────────
  { plan: 'Blue Cross Blue Shield of Massachusetts',           family: 'BCBS',    col: 34 },
  { plan: 'Anthem Blue Cross and Blue Shield (Colorado)',      family: 'BCBS',    col: 38 },
  { plan: 'Anthem Blue Cross and Blue Shield (Connecticut)',   family: 'BCBS',    col: 42 },
  { plan: 'Anthem Blue Cross and Blue Shield (Maine)',         family: 'BCBS',    col: 46 },
  { plan: 'Anthem Blue Cross and Blue Shield (Nevada)',        family: 'BCBS',    col: 50 },
  { plan: 'Anthem Blue Cross and Blue Shield (New Hampshire)', family: 'BCBS',    col: 54 },
  { plan: 'Anthem Blue Cross Blue Shield (Indiana)',           family: 'BCBS',    col: 58 },
  { plan: 'Blue Cross and Blue Shield of Minnesota',           family: 'BCBS',    col: 62 },
  { plan: 'Blue Cross Blue Shield of Arizona',                 family: 'BCBS',    col: 66 },
  { plan: 'Florida Blue',                                      family: 'BCBS',    col: 70 },
  { plan: 'Florida Blue Medicare Advantage',                   family: 'BCBS',    col: 74 },
  { plan: 'Horizon Blue Cross and Blue Shield of New Jersey',  family: 'BCBS',    col: 78 },
  { plan: 'Independence Blue Cross Pennsylvania',              family: 'BCBS',    col: 82 },
  { plan: 'Regence BlueShield of Washington',                  family: 'BCBS',    col: 86 },
  { plan: 'Regence BlueCross BlueShield of Oregon',            family: 'BCBS',    col: 90 },
  { plan: 'Premera Blue Cross Washington',                     family: 'BCBS',    col: 94 },
  { plan: 'Ambetter (Washington)',                             family: 'BCBS',    col: 98 },
];

var TOTAL_COLS     = 101;  // col A (label) + 25 plans × 4 cols = 101
var ROWS_PER_STATE = 8;    // label, date, 5 CPTs, blank separator
var HEADER_ROWS    = 2;    // row 1 = plan names, row 2 = Alma/HW/Grow/SBH labels
var SUB_COLS       = ['Alma', 'Headway', 'Grow', 'SBH'];

// Family header background colors (light pastels)
var FAMILY_COLORS = {
  'Optum':    '#D6EAF8',  // light blue
  'Aetna':    '#FADBD8',  // light red/pink
  'Cigna':    '#FDEBD0',  // light orange
  'Carelon':  '#E8DAEF',  // light purple
  'Wellmark': '#D5F5E3',  // light green
  'BCBS':     '#FEF9E7',  // light yellow
};

// Old MASTER state-to-row mapping (1-indexed, includes KS/ME/VT)
var OLD_STATE_TO_ROW = {
  AK: 3,  AZ: 11, CO: 19,  FL: 27,  HI: 35,  ID: 43,  IA: 51,  MD: 59,
  MN: 67, MT: 75, NE: 83,  NV: 91,  NM: 99,  ND: 107, OR: 115, SD: 123,
  WA: 131,DC: 139,WY: 147, KS: 155, NH: 163, ME: 171, VT: 179, CT: 187, UT: 195,
};


// ══════════════════════════════════════════════════════════════
//  MAIN ENTRY POINT
// ══════════════════════════════════════════════════════════════

function buildNewMasterSheet() {
  // 1. Load old MASTER data (one read call)
  Logger.log('Loading old MASTER data...');
  var oldSS    = SpreadsheetApp.openById(OLD_MASTER_ID);
  var oldSheet = oldSS.getSheetByName(OLD_MASTER_TAB);
  var oldData  = oldSheet.getRange(1, 1, 210, 30).getValues();

  // 2. Create new spreadsheet
  Logger.log('Creating new Google Spreadsheet...');
  var newSS = SpreadsheetApp.create('Solrei MASTER Rates — New Design');
  var sheet = newSS.getActiveSheet();
  sheet.setName('Rates');

  Logger.log('New sheet URL: ' + newSS.getUrl());

  // 3. Expand sheet to 101 columns (new sheets only have 26 by default)
  var currentCols = sheet.getMaxColumns();
  if (currentCols < TOTAL_COLS) {
    sheet.insertColumnsAfter(currentCols, TOTAL_COLS - currentCols);
  }

  // 4. Freeze panes and set column widths
  sheet.setFrozenRows(HEADER_ROWS);
  sheet.setFrozenColumns(1);
  sheet.setColumnWidth(1, 90);
  for (var c = 2; c <= TOTAL_COLS; c++) {
    sheet.setColumnWidth(c, 70);
  }

  // 5. Build header rows (plan names row + sub-col labels row)
  Logger.log('Building headers...');
  _buildHeaders(sheet);

  // 6. Build state blocks with migrated data
  Logger.log('Building state blocks and migrating data...');
  _buildStateBlocks(sheet, oldData);

  // 7. Apply number formatting to all data cells
  var firstDataRow = HEADER_ROWS + 1;
  var totalStateRows = STATES.length * ROWS_PER_STATE;
  sheet.getRange(firstDataRow, 2, totalStateRows, TOTAL_COLS - 1)
       .setNumberFormat('[$$-409]#,##0.00;-[$$-409]#,##0.00');

  // 8. Apply conditional formatting (green = max per 4-col group per row)
  Logger.log('Applying conditional formatting...');
  _applyConditionalFormatting(sheet, firstDataRow, firstDataRow + totalStateRows - 1);

  // 9. Done
  Logger.log('Complete! New MASTER sheet: ' + newSS.getUrl());
  SpreadsheetApp.getUi().alert(
    '✓ New MASTER sheet created!\n\n' +
    newSS.getUrl() + '\n\n' +
    '• Old MASTER was NOT modified\n' +
    '• Existing data migrated where column mapping was known\n' +
    '• Green highlighting = highest rate per plan group per row'
  );
}


// ══════════════════════════════════════════════════════════════
//  BUILD HEADER ROWS
// ══════════════════════════════════════════════════════════════

function _buildHeaders(sheet) {
  // Row 1: plan names (one per 4-col group, others blank — will be merged)
  var r1 = new Array(TOTAL_COLS).fill('');
  r1[0] = 'State / CPT';
  for (var i = 0; i < PLAN_GROUPS.length; i++) {
    r1[PLAN_GROUPS[i].col - 1] = PLAN_GROUPS[i].plan;
  }

  // Row 2: sub-column labels (Alma, Headway, Grow, SBH repeated per group)
  var r2 = new Array(TOTAL_COLS).fill('');
  for (var i = 0; i < PLAN_GROUPS.length; i++) {
    var base = PLAN_GROUPS[i].col - 1; // 0-indexed
    for (var s = 0; s < SUB_COLS.length; s++) {
      r2[base + s] = SUB_COLS[s];
    }
  }

  sheet.getRange(1, 1, 1, TOTAL_COLS).setValues([r1]);
  sheet.getRange(2, 1, 1, TOTAL_COLS).setValues([r2]);

  // Row heights
  sheet.setRowHeight(1, 52);
  sheet.setRowHeight(2, 20);

  // Label column header (A1:A2)
  sheet.getRange(1, 1, 2, 1)
       .setBackground('#2C3E50')
       .setFontColor('#FFFFFF')
       .setFontWeight('bold')
       .setFontSize(9)
       .setHorizontalAlignment('center')
       .setVerticalAlignment('middle');

  // Per-plan-group formatting: merge row-1 cells, apply family color
  for (var i = 0; i < PLAN_GROUPS.length; i++) {
    var pg    = PLAN_GROUPS[i];
    var col   = pg.col;
    var color = FAMILY_COLORS[pg.family] || '#FFFFFF';

    // Merge plan name across 4 columns in row 1
    var r1group = sheet.getRange(1, col, 1, 4);
    r1group.mergeAcross();
    r1group.setValue(pg.plan)
           .setBackground(color)
           .setFontWeight('bold')
           .setFontSize(8)
           .setHorizontalAlignment('center')
           .setVerticalAlignment('middle')
           .setWrap(true)
           .setFontFamily('Arial');

    // Sub-column labels row 2
    var r2group = sheet.getRange(2, col, 1, 4);
    r2group.setBackground(color)
           .setFontWeight('bold')
           .setFontSize(9)
           .setHorizontalAlignment('center')
           .setFontFamily('Arial');

    // SBH sub-column in dark red to distinguish it
    sheet.getRange(2, col + 3)
         .setFontColor('#8B0000')
         .setFontWeight('bold');
  }

  // Light border between family groups
  var familyBoundaries = [2, 6, 10, 14, 18, 22, 26, 30, 34, 98]; // col starts
  for (var i = 0; i < familyBoundaries.length; i++) {
    var bc = familyBoundaries[i];
    if (bc <= TOTAL_COLS) {
      sheet.getRange(1, bc, 2, 1)
           .setBorder(null, true, null, null, null, null, '#888888',
                      SpreadsheetApp.BorderStyle.SOLID_MEDIUM);
    }
  }
}


// ══════════════════════════════════════════════════════════════
//  BUILD STATE BLOCKS
// ══════════════════════════════════════════════════════════════

function _buildStateBlocks(sheet, oldData) {
  var startRow = HEADER_ROWS + 1; // row 3 = first state block

  for (var si = 0; si < STATES.length; si++) {
    var stateCode    = STATES[si][0];
    var stateName    = STATES[si][1];
    var blockStart   = startRow + si * ROWS_PER_STATE;
    var stateRow     = blockStart;      // row for state label
    var dateRow      = blockStart + 1;  // row for effective dates

    // ── State label row (blue banner) ──────────────────────
    sheet.setRowHeight(stateRow, 18);
    sheet.getRange(stateRow, 1, 1, TOTAL_COLS)
         .setBackground('#2980B9')
         .setFontColor('#FFFFFF')
         .setFontWeight('bold')
         .setFontSize(9);
    sheet.getRange(stateRow, 1)
         .setValue(stateCode + '  —  ' + stateName)
         .setHorizontalAlignment('left');

    // ── Date row ───────────────────────────────────────────
    sheet.setRowHeight(dateRow, 16);
    sheet.getRange(dateRow, 1, 1, TOTAL_COLS)
         .setBackground('#EBF5FB')
         .setFontSize(8)
         .setFontStyle('italic');
    sheet.getRange(dateRow, 1)
         .setValue('Date')
         .setHorizontalAlignment('right');

    // ── CPT code rows ──────────────────────────────────────
    for (var ci = 0; ci < CPT_CODES.length; ci++) {
      var cptRow = blockStart + 2 + ci;
      sheet.setRowHeight(cptRow, 18);
      sheet.getRange(cptRow, 1)
           .setValue(CPT_CODES[ci])
           .setHorizontalAlignment('center')
           .setFontSize(9)
           .setFontWeight('normal');
      // Alternate shading
      if (ci % 2 === 1) {
        sheet.getRange(cptRow, 2, 1, TOTAL_COLS - 1)
             .setBackground('#F7FBFF');
      }
    }

    // ── Blank separator row ────────────────────────────────
    sheet.setRowHeight(blockStart + 7, 5);

    // ── Migrate data from old MASTER ───────────────────────
    if (OLD_STATE_TO_ROW[stateCode] !== undefined) {
      _migrateStateData(sheet, oldData, stateCode,
                        OLD_STATE_TO_ROW[stateCode], blockStart, dateRow);
    }
  }
}


// ══════════════════════════════════════════════════════════════
//  DATA MIGRATION FROM OLD MASTER
// ══════════════════════════════════════════════════════════════

function _migrateStateData(sheet, oldData, stateCode, oldStateRow, newBlockStart, newDateRow) {
  /**
   * oldStateRow:   1-indexed state-start row in old MASTER
   * oldData:       0-indexed array (oldData[0] = sheet row 1)
   *
   * In v5/v6, masterData[stateRow] = date row (0-indexed stateRow maps to sheet row stateRow+1)
   * BUT: oldStateRow is the label row (e.g. AK=3), so:
   *   - Old date row:      oldData[oldStateRow]     (0-indexed = label row index + 1)
   *   - Old CPT row (99214): oldData[oldStateRow + CPT_OFFSET - 1]
   *
   * New sheet:
   *   - newBlockStart = state label row (1-indexed)
   *   - newDateRow    = newBlockStart + 1
   *   - CPT rows      = newBlockStart + 2 through newBlockStart + 6
   */

  // Universal column mappings (same regardless of state)
  // Format: [oldCol_1indexed, newCol_1indexed]
  var universalMap = [
    [2,  2],   // UHC/Oscar/Optum → Alma
    [3,  3],   // UHC/Oscar/Optum → Headway
    [4,  4],   // UHC/Oscar/Optum → Grow
    [5,  5],   // UHC/Oscar/Optum → SBH
    [6,  18],  // Aetna → Alma
    [7,  19],  // Aetna → Headway
    [8,  20],  // Aetna → Grow
    [9,  21],  // Aetna → SBH
    [10, 22],  // Cigna → Alma
    [11, 23],  // Cigna → Headway
    [12, 24],  // Cigna → Grow
    [13, 25],  // Cigna → SBH
  ];

  // State-specific additional column mappings
  // Old MASTER col 14 = Alma for BCBS-family plan (varies by state)
  // Old MASTER col 17 = BCBS MA SBH (only states where BCBS MA was tracked)
  // Old MASTER cols 18-23 = state-specific Headway plans
  var stateExtraMap = {
    'AK': [
      [14, 34],  // BCBS MA Alma (col 34 = BCBS MA group, Alma sub-col)
      [17, 37],  // BCBS MA SBH
      [18, 79],  // Horizon NJ Headway
      [19, 83],  // Independence PA Headway
    ],
    'AZ': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 67],  // BCBS AZ Headway
    ],
    'CO': [
      [14, 38],  // Anthem CO Alma
      // Old col 18 = Anthem CO HMO Headway, col 19 = Anthem CO PPO Headway
      // New design has one Anthem CO Headway col (39); map HMO only to avoid overwrite
      [18, 39],  // Anthem CO HMO → Anthem CO Headway
    ],
    'CT': [
      [14, 42],  // Anthem CT Alma
    ],
    'FL': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [19, 71],  // Florida Blue Headway
      [20, 75],  // Florida Blue Medicare Advantage Headway
      [21, 79],  // Horizon NJ Headway
      [22, 83],  // Independence PA Headway
      [23, 59],  // Anthem Indiana Headway
    ],
    'IA': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
    ],
    'MN': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 63],  // BCBS Minnesota Headway
      // Old cols 19 (BCBS MN Medicaid) & 20 (BCBS MN MA) — no separate cols in new design
    ],
    'NH': [
      [14, 54],  // Anthem NH Alma
      [18, 95],  // Premera WA Headway
    ],
    'NM': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
    ],
    'NV': [
      [14, 50],  // Anthem NV Alma
    ],
    'OR': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 91],  // Regence OR Headway
    ],
    'WA': [
      [14, 34],  // BCBS MA Alma
      [17, 37],  // BCBS MA SBH
      [18, 35],  // BCBS MA Headway (WA is the only state with BCBS MA via Headway)
      [19, 79],  // Horizon NJ Headway
      [20, 83],  // Independence PA Headway
      [21, 87],  // Regence WA Headway
      [22, 95],  // Premera WA Headway
    ],
  };

  // Combine universal + state-specific mappings
  var colMap = universalMap.slice();
  if (stateExtraMap[stateCode]) {
    colMap = colMap.concat(stateExtraMap[stateCode]);
  }

  // ── Migrate dates ─────────────────────────────────────────
  // Old date row: oldData[oldStateRow] (stateRow is 0-indexed here because
  // oldData uses 0-based indexing and stateRow=3 points to oldData[3]=row 4=date row)
  var oldDateIdx = oldStateRow; // 0-indexed offset into oldData
  var dateUpdates = [];

  for (var m = 0; m < colMap.length; m++) {
    var oldCol0 = colMap[m][0] - 1; // 0-indexed column
    var newCol1 = colMap[m][1];     // 1-indexed column
    var dateVal = oldData[oldDateIdx][oldCol0];
    if (dateVal && String(dateVal).trim() !== '') {
      dateUpdates.push({ row: newDateRow, col: newCol1, val: dateVal });
    }
  }

  // ── Migrate CPT rows ──────────────────────────────────────
  var cptUpdates = [];

  for (var ci = 0; ci < CPT_CODES.length; ci++) {
    var cpt          = CPT_CODES[ci];
    var oldCptIdx    = oldStateRow + CPT_OFFSETS[cpt] - 1; // 0-indexed in oldData
    var newCptRow    = newBlockStart + 2 + ci;             // 1-indexed in new sheet

    for (var m = 0; m < colMap.length; m++) {
      var oldCol0 = colMap[m][0] - 1;
      var newCol1 = colMap[m][1];
      var val     = oldData[oldCptIdx][oldCol0];

      if (typeof val === 'number' && !isNaN(val) && val > 0) {
        cptUpdates.push({ row: newCptRow, col: newCol1, val: val });
      }
    }
  }

  // Write all updates (cell-by-cell — acceptable for a one-time migration)
  for (var i = 0; i < dateUpdates.length; i++) {
    sheet.getRange(dateUpdates[i].row, dateUpdates[i].col)
         .setValue(dateUpdates[i].val);
  }
  for (var i = 0; i < cptUpdates.length; i++) {
    sheet.getRange(cptUpdates[i].row, cptUpdates[i].col)
         .setValue(cptUpdates[i].val);
  }
}


// ══════════════════════════════════════════════════════════════
//  CONDITIONAL FORMATTING — green = max per 4-col group per row
// ══════════════════════════════════════════════════════════════

function _applyConditionalFormatting(sheet, firstDataRow, lastDataRow) {
  /**
   * Formula logic (anchored at B + firstDataRow):
   *   COLUMN(B) = 2, so COLUMN()-2 = 0 → MOD(0,4)=0 → OFFSET back 0 → group starts at B
   *   COLUMN(C) = 3, so COLUMN()-2 = 1 → MOD(1,4)=1 → OFFSET back 1 → group starts at B
   *   COLUMN(D) = 4, so COLUMN()-2 = 2 → MOD(2,4)=2 → OFFSET back 2 → group starts at B
   *   COLUMN(E) = 5, so COLUMN()-2 = 3 → MOD(3,4)=3 → OFFSET back 3 → group starts at B
   *   COLUMN(F) = 6, so COLUMN()-2 = 4 → MOD(4,4)=0 → OFFSET back 0 → group starts at F ✓
   *
   * This correctly identifies the start of each 4-col group for any column ≥ B.
   * ISNUMBER() prevents highlighting on state label and date rows (non-numeric).
   */
  var anchorCell = 'B' + firstDataRow;
  var formula = '=AND(ISNUMBER(' + anchorCell + '),' +
                anchorCell + '=MAX(OFFSET(' + anchorCell + ',0,' +
                '-MOD(COLUMN(' + anchorCell + ')-2,4),1,4)))';

  var dataRange = sheet.getRange(firstDataRow, 2,
                                 lastDataRow - firstDataRow + 1,
                                 TOTAL_COLS - 1);

  var rule = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied(formula)
    .setBackground('#00B050')   // Excel "green" fill
    .setFontColor('#FFFFFF')
    .setRanges([dataRange])
    .build();

  var rules = sheet.getConditionalFormatRules();
  rules.push(rule);
  sheet.setConditionalFormatRules(rules);
}


// ══════════════════════════════════════════════════════════════
//  UTILITY: Re-apply formatting to an existing new MASTER sheet
//  Run this if you want to reapply conditional formatting only
// ══════════════════════════════════════════════════════════════

function reapplyConditionalFormatting() {
  var sheet        = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Rates');
  var firstDataRow = HEADER_ROWS + 1;
  var lastDataRow  = firstDataRow + STATES.length * ROWS_PER_STATE - 1;
  sheet.clearConditionalFormatRules();
  _applyConditionalFormatting(sheet, firstDataRow, lastDataRow);
  SpreadsheetApp.getActiveSpreadsheet()
    .toast('Conditional formatting reapplied.', 'Done', 5);
}


// ══════════════════════════════════════════════════════════════
//  MENU
// ══════════════════════════════════════════════════════════════

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('Solrei MASTER Builder')
    .addItem('Build New MASTER Sheet', 'buildNewMasterSheet')
    .addSeparator()
    .addItem('Reapply Conditional Formatting (active sheet)', 'reapplyConditionalFormatting')
    .addToUi();
}
