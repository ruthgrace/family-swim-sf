# PDF Parsing Improvements - November 2025

## Problem Identified

The swim schedule scraper was extracting incorrect data from pool schedule PDFs. Specifically for Coffman Pool, the data showed times on wrong days (e.g., Wednesday times appearing on Friday, Thursday showing family swim when there was none).

**Root Cause**: Claude was misreading multi-column PDF tables, confusing which times belonged to which day columns.

## Investigation Summary

### 1. Verified PDF Selection & Download (Working Correctly ✓)
- The script correctly finds documents on facility pages
- It properly selects the most recent/relevant PDF (e.g., "Coffman Pool_Fall25_Aug19_Dec27")
- The download function works correctly and follows redirects
- The correct Fall 2025 PDF was being processed

### 2. Initial Approach: Direct JSON Extraction (❌ Failed)
- Asked Claude to extract all days at once and return JSON
- Result: Severe column confusion - nearly all days had wrong times
- Example: Wednesday times appearing on Friday, Thursday showing family swim when none existed

### 3. Second Approach: Markdown-First (⚠️ Partial Success)
**Implementation**:
- Added `pdf_table_to_markdown()` function to convert PDF table to markdown first
- Added `parse_markdown_schedule()` to parse the markdown with Python code
- This allowed us to see what Claude was "reading" before parsing

**Results**:
- Helped debug the issue by showing Claude's interpretation
- Still had column alignment errors in the markdown conversion
- Claude was still mixing up adjacent columns (e.g., putting Saturday times in Friday)

### 4. Third Approach: Day-by-Day Extraction (✓ Best Results)
**Implementation**:
- Added `extract_single_day_schedule()` - makes one API call per day
- Added `extract_family_swim_day_by_day()` - orchestrates 7 separate extractions
- Each call asks Claude to focus on ONLY one specific day column
- Improved JSON extraction to handle Claude's explanatory text

**Results for Coffman Pool**:
- ✓ Tuesday: CORRECT (2:00PM-4:00PM REC/FAMILY SWIM)
- ✓ Wednesday: CORRECT (1:30PM-2:30PM REC/FAMILY SWIM)
- ✓ Thursday: CORRECT (no family swim)
- ❌ Friday: WRONG (extracted 1:00PM-2:00PM + 2:30PM-3:45PM from Saturday column instead of 2:00PM-3:00PM)
- ✓ Saturday: CORRECT (1:00PM-2:00PM PARENT & CHILD, 2:30PM-3:45PM REC/FAMILY)
- ✓ Sunday: CORRECT (no swims)
- ✓ Monday: CORRECT (no swims)

**Accuracy: 5 out of 7 days (71%) vs 0 out of 7 days (0%) with original approach**

## Code Changes

### New Functions Added to `pdf_parser.py`:

1. **`extract_single_day_schedule(pdf_path, pool_name, weekday)`**
   - Extracts schedule for one specific day
   - Returns list of swim slots for that day
   - Includes improved JSON extraction to handle Claude's explanatory text

2. **`extract_family_swim_day_by_day(pdf_path, pool_name)`**
   - Calls `extract_single_day_schedule()` for each day of the week
   - Returns complete schedule in standard format

3. **`pdf_table_to_markdown(pdf_path, pool_name)`**
   - Converts PDF schedule table to markdown format (kept for debugging/fallback)

4. **`parse_markdown_schedule(markdown_text, pool_name)`**
   - Parses markdown table into schedule data (kept for fallback)

### Modified Function:

**`get_pool_schedule_from_pdf()`**
- Now uses day-by-day approach as primary method
- Falls back to markdown approach if day-by-day fails
- Falls back to direct extraction if markdown fails
- Three-tier fallback strategy for robustness

## Current Status

**Deployed**: No - changes are in `pdf_parser.py` but not committed or deployed

**Recommendation**: The day-by-day approach shows significant improvement (0% → 71% accuracy) but still has column confusion issues on some days.

### Options Going Forward:

1. **Deploy Current Solution**: Accept 71% accuracy as much better than 0%
2. **Further Improvements**:
   - Try asking Claude to describe column positions before extraction
   - Use OCR with explicit coordinate-based extraction
   - Add manual correction rules for known problem cases
3. **Test on Other Pools**: Run full scraper to see if Coffman Pool's Friday issue is unique or systemic

## Files Modified

- `pdf_parser.py` - Added new extraction methods and improved JSON parsing

## Files Not Modified (Unchanged)

- `main.py` - Main scraper script
- `pool_sources.json` - Pool facility URLs
- All map data files - Not updated with new extraction

## Technical Notes

- Day-by-day approach makes 7 API calls per pool instead of 1 (higher cost/latency)
- However, the accuracy improvement justifies the additional API calls
- The fundamental issue is Claude's difficulty with multi-column PDF tables, even when explicitly instructed to focus on one column
- Adjacent columns (like Friday/Saturday) are more prone to confusion than non-adjacent ones
