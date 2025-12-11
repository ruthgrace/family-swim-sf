"""
PDF parsing utilities for extracting pool schedules

Simplified Multi-Pass Strategy:
1. Extract RAW schedule from PDF (Claude Sonnet 4.5 - vision only, no filtering)
2. Filter for family/parent-child swim (Claude Sonnet 4 - JSON filtering, excludes classes)
3. Extract lap swim from raw schedule (Python - no API call)
4. Extract all activities from raw schedule (Python - no API call)
5. Calculate secret swims (Claude Sonnet 4 - AI analysis with pool-specific rules)
6. Combine and sort schedules (Python - merge and sort by start time)

This approach uses AI strategically: vision extraction, intelligent filtering, and rule-based analysis.
"""

import re
import requests
import traceback
import json
import base64
import os
from bs4 import BeautifulSoup
from anthropic import Anthropic
from constants import ANTHROPIC_API_KEY
import pypdfium2 as pdfium

# Cache file for storing PDF lists and parsed schedules
CACHE_FILE = "map_data/pdf_schedule_cache.json"


def load_cache():
    """Load the PDF schedule cache from disk."""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load cache: {e}")
    return {}


def save_cache(cache):
    """Save the PDF schedule cache to disk."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save cache: {e}")


def get_pdf_list_signature(documents, pool_name, search_terms):
    """
    Get a signature of the PDFs available for a pool.
    Returns a sorted list of PDF names that match the pool's search terms.
    """
    matching_pdfs = []
    for doc in documents:
        doc_name_lower = doc['name'].lower()
        if any(term in doc_name_lower for term in search_terms):
            matching_pdfs.append(doc['name'])
    return sorted(matching_pdfs)


def get_facility_documents(facility_url):
    """Scrape a facility page and extract all documents"""
    try:
        response = requests.get(facility_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        documents = []
        doc_links = soup.find_all('a', href=lambda href: href and '/DocumentCenter/View/' in href)

        for link in doc_links:
            doc_name = link.get_text(strip=True)
            doc_url = link.get('href')

            if doc_url.startswith('/'):
                doc_url = f"https://sfrecpark.org{doc_url}"

            documents.append({'name': doc_name, 'url': doc_url})

        return documents
    except Exception as e:
        print(f"Error fetching documents: {e}")
        traceback.print_exc()
        return []


def select_schedule_pdf(documents, pool_name, current_date, pools_list):
    """Filter documents for schedule PDFs and select the most appropriate one based on date ranges"""
    schedule_docs = []
    pool_name_lower = pool_name.lower()
    pool_name_base = pool_name_lower.replace(' pool', '')

    # Special abbreviations and partial name mappings
    pool_name_variants = {
        'martin luther king jr': ['mlk'],
        'mission community': ['mission'],
    }

    # Get all matching variants for this pool
    search_terms = [pool_name_lower, pool_name_base]
    for key, variants in pool_name_variants.items():
        if key in pool_name_lower:
            search_terms.extend(variants)

    # Log all documents found for debugging
    print(f"  Documents on page: {[d['name'] for d in documents]}")
    print(f"  Search terms: {search_terms}")

    for doc in documents:
        doc_name_lower = doc['name'].lower()
        if any(term in doc_name_lower for term in search_terms):
            other_pools = [p.lower() for p in pools_list if p.lower() != pool_name_lower]
            is_other_pool = any(other_pool in doc_name_lower for other_pool in other_pools)

            if not is_other_pool:
                schedule_docs.append(doc)
            else:
                print(f"  Rejected '{doc['name']}' - matches another pool name")
        else:
            # Only log non-empty document names that didn't match
            if doc['name'].strip():
                print(f"  Skipped '{doc['name']}' - no search term match")

    print(f"  Candidate schedule PDFs: {[d['name'] for d in schedule_docs]}")

    if not schedule_docs:
        print(f"  No candidate PDFs found for {pool_name}")
        return None

    # Use Claude to validate PDF date ranges and select a valid one
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        doc_list = "\n".join([f"{i+1}. {doc['name']}" for i, doc in enumerate(schedule_docs)])

        prompt = f"""Today's date: {current_date.strftime('%B %d, %Y')}

Pool: {pool_name}
Documents:
{doc_list}

Task: Find which document covers TODAY's date ({current_date.strftime('%B %d, %Y')}).

Date parsing examples:
- "Fall25_Aug19_Dec27" = Aug 19, 2025 to Dec 27, 2025
- "Fall25_Nov1_Nov22" = Nov 1, 2025 to Nov 22, 2025 (EXPIRED if today is after Nov 22)
- "Fall 2025" with no specific dates = Sep 1 to Dec 31, 2025

STEP BY STEP:
1. Parse each document's date range from its filename
2. Check: Is {current_date.strftime('%B %d, %Y')} between the start and end dates?
3. If YES for any document, reply with that document number
4. If NO document covers today (all expired or no dates), reply NONE

Your answer will be parsed by code. You must reply with ONLY the index value in digit form, or NONE. Do NOT include any other text in your response."""

        # Retry loop for flaky responses (e.g., Claude returns verbose text with year "2025" instead of "1")
        for attempt in range(3):  # Up to 3 attempts (1 initial + 2 retries)
            message = client.messages.create(
                model="claude-sonnet-4-5-20250929",  # Using Sonnet for date range matching (Haiku struggles with date comparisons)
                max_tokens=10,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "Answer:"}  # Prefill to force concise response
                ]
            )

            raw_response = message.content[0].text.strip()
            print(f"  Claude date selection response: '{raw_response}'")

            # Extract number or NONE from response using regex
            # Look for NONE first
            if re.search(r'\bNONE\b', raw_response, re.IGNORECASE):
                print(f"No valid schedule PDF for {pool_name} on {current_date.strftime('%B %d, %Y')}")
                return None

            # Look for a number (1, 2, 3, etc.)
            number_match = re.search(r'\b(\d+)\b', raw_response)
            if number_match:
                selected_index = int(number_match.group(1)) - 1
                if 0 <= selected_index < len(schedule_docs):
                    selected = schedule_docs[selected_index]
                    print(f"Selected: {selected['name']}")
                    return selected
                else:
                    print(f"  Attempt {attempt + 1}: Invalid index {selected_index + 1} (only {len(schedule_docs)} candidates), retrying...")
                    continue
            else:
                # No number found, retry
                print(f"  Attempt {attempt + 1}: No number in response, retrying...")
                continue

    except Exception as e:
        print(f"Warning: Claude selection failed ({e}), returning None")

    # Fallback: return None instead of first doc (safer default)
    print(f"Could not determine valid PDF for {pool_name}")
    return None


def download_pdf(pdf_url, output_path):
    """Download a PDF from the given URL"""
    try:
        response = requests.get(pdf_url)
        response.raise_for_status()

        with open(output_path, 'wb') as f:
            f.write(response.content)

        return True
    except Exception as e:
        print(f"Error downloading PDF: {e}")
        traceback.print_exc()
        return False


def convert_pdf_to_image(pdf_path, output_path=None, dpi=300):
    """
    Convert first page of PDF to high-resolution PNG image.

    Args:
        pdf_path: Path to PDF file
        output_path: Optional output path for PNG. If None, uses pdf_path with .png extension
        dpi: Resolution for rendering (default 300 for high quality)

    Returns:
        Path to the generated PNG file, or None if failed
    """
    try:
        if output_path is None:
            output_path = pdf_path.rsplit('.', 1)[0] + '_page1.png'

        pdf = pdfium.PdfDocument(pdf_path)
        page = pdf[0]  # Get first page

        # Render at specified DPI (default PDF DPI is 72)
        bitmap = page.render(scale=dpi/72)
        pil_image = bitmap.to_pil()

        # Save as PNG
        pil_image.save(output_path)

        print(f"Converted PDF to image: {output_path} (size: {pil_image.size})")
        return output_path
    except Exception as e:
        print(f"Error converting PDF to image: {e}")
        traceback.print_exc()
        return None


def time_to_minutes(time_str):
    """Convert time string like '9:00AM' to minutes since midnight"""
    time_str = time_str.upper().strip()
    if time_str == "NOON":
        return 12 * 60

    is_pm = time_str.endswith('PM')
    time_str = time_str.replace('AM', '').replace('PM', '')

    parts = time_str.split(':')
    hours = int(parts[0])
    minutes = int(parts[1]) if len(parts) > 1 else 0

    if is_pm and hours != 12:
        hours += 12
    elif not is_pm and hours == 12:
        hours = 0

    return hours * 60 + minutes


def minutes_to_time(minutes):
    """Convert minutes since midnight to time string like '9:00AM'"""
    hours = minutes // 60
    mins = minutes % 60

    is_pm = hours >= 12
    if hours > 12:
        hours -= 12
    elif hours == 0:
        hours = 12

    period = 'PM' if is_pm else 'AM'
    return f"{hours}:{mins:02d}{period}"


def conflicts_with_small_pool(activity):
    """
    Check if activity conflicts with Secret Swim in Small Pool.

    Returns True (conflict) if:
    - Activity explicitly uses Small Pool
    - Activity has no specified location (uses whole pool)

    Returns False (no conflict) if:
    - Activity explicitly uses Main Pool only
    - Activity explicitly uses specific lanes (e.g., "(4)", "(2)")
    """
    pool_area = activity.get("pool_area", "").strip().lower()

    # Explicit Small Pool - conflicts
    if "small pool" in pool_area:
        return True

    # Explicit Main Pool - no conflict
    if "main pool" in pool_area:
        return False

    # Lane counts (e.g., "(4)", "(2)", "(6)") - Main Pool only, no conflict
    if re.search(r'\(\d+\)', pool_area):
        return False

    # No location specified - uses whole pool, CONFLICTS
    if not pool_area:
        return True

    # Any other explicit location - assume no conflict
    return False


def times_overlap(act1, act2):
    """Check if two activities have overlapping times."""
    start1 = time_to_minutes(act1["start"])
    end1 = time_to_minutes(act1["end"])
    start2 = time_to_minutes(act2["start"])
    end2 = time_to_minutes(act2["end"])

    return start1 < end2 and start2 < end1


def calculate_balboa_secret_swim(raw_schedule, pool_name):
    """
    Deterministic secret swim calculation for Balboa Pool.

    Secret swim ("Parent Child Swim on Steps") is available during LAP SWIM times
    ONLY when no other activity overlaps with the lap swim slot.
    """
    secret_swim_data = {
        "Saturday": [], "Sunday": [], "Monday": [],
        "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": []
    }

    for day, activities in raw_schedule.items():
        if day not in secret_swim_data:
            continue

        # Find all lap swim slots for this day
        lap_swims = [a for a in activities if 'lap swim' in a.get('activity', '').lower()]

        for lap_swim in lap_swims:
            # Check if any OTHER activity overlaps with this lap swim
            has_conflict = False
            for other in activities:
                # Skip the lap swim itself
                if 'lap swim' in other.get('activity', '').lower():
                    continue
                # Check for time overlap
                if times_overlap(lap_swim, other):
                    has_conflict = True
                    break

            # If no conflict, add secret swim
            if not has_conflict:
                secret_swim_data[day].append({
                    "pool": pool_name,
                    "weekday": day,
                    "start": lap_swim["start"],
                    "end": lap_swim["end"],
                    "note": "Parent Child Swim on Steps"
                })

    return secret_swim_data


def calculate_garfield_secret_swim(raw_schedule, pool_name):
    """
    Deterministic secret swim calculation for Garfield Pool.

    For each activity that does NOT conflict with the Small Pool,
    check if any overlapping activity DOES conflict. If no conflict,
    that time slot gets secret swim.
    """
    secret_swim_data = {
        "Saturday": [], "Sunday": [], "Monday": [],
        "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": []
    }

    for day, activities in raw_schedule.items():
        if day not in secret_swim_data:
            continue

        # Track added time slots to avoid duplicates
        added_slots = set()

        for activity in activities:
            # Step 1: Skip if this activity conflicts with Small Pool
            if conflicts_with_small_pool(activity):
                continue

            # Step 2: Check for overlapping activities that conflict
            has_conflict = False
            for other in activities:
                if other == activity:
                    continue
                if conflicts_with_small_pool(other) and times_overlap(activity, other):
                    has_conflict = True
                    break

            # Step 3: If no conflict, add secret swim (with deduplication)
            if not has_conflict:
                slot_key = (activity["start"], activity["end"])
                if slot_key not in added_slots:
                    added_slots.add(slot_key)
                    secret_swim_data[day].append({
                        "pool": pool_name,
                        "weekday": day,
                        "start": activity["start"],
                        "end": activity["end"],
                        "note": "Parent Child Swim in Small Pool"
                    })

    return secret_swim_data


def parse_json_response(response_text):
    """Helper function to extract JSON from API response text."""
    if '```json' in response_text:
        start = response_text.find('```json') + 7
        end = response_text.find('```', start)
        if end != -1:
            return response_text[start:end].strip()
    elif '```' in response_text:
        start = response_text.find('```') + 3
        end = response_text.rfind('```')
        if end != -1 and end > start:
            return response_text[start:end].strip()
    elif '[' in response_text and ']' in response_text:
        start = response_text.find('[')
        end = response_text.rfind(']') + 1
        return response_text[start:end].strip()
    return response_text


def get_extraction_prompt(pool_name, day, direction="top-down"):
    """Generate extraction prompt for a specific day and direction."""
    if direction == "bottom-up":
        direction_instructions = """CRITICAL: Read the column from BOTTOM TO TOP. Start at the bottom row and work your way up, then output in chronological order.

STEP-BY-STEP PROCESS:
1. Locate the {day} column header
2. Go to the BOTTOM of that column
3. Starting from the BOTTOM row, read each activity cell moving UPWARD
4. For EACH cell:
   a. FIRST: Look up to confirm you're still in the {day} column - what is the header directly above?
   b. VERIFY: Double-check the column header says {day}
   c. ONLY THEN: Extract the activity details
5. DO NOT drift into adjacent columns - stay within vertical boundaries
6. If a cell has multiple activities (e.g., "MAIN POOL - LAP SWIM" and "SMALL POOL - FAMILY SWIM"), extract them as SEPARATE entries
7. Output in chronological order (earliest first) when done""".format(day=day.upper())
    else:
        direction_instructions = """CRITICAL INSTRUCTIONS FOR READING THE {day} COLUMN:
⚠️ COMMON ERROR: Accidentally reading activities from adjacent columns. You MUST only include activities that are directly below the column header for {day} only. Pools are closed some days of the week, so if there is no column header with {day}, please simply return an empty array.

STEP-BY-STEP PROCESS:
1. Locate the {day} column header
2. Draw an imaginary vertical line straight down from that header
3. For EACH activity cell in that column:
   a. FIRST: Look up to confirm you're still in the {day} column - what is the header directly above?
   b. VERIFY: Double-check the column header says {day}
   c. ONLY THEN: Extract the activity details
4. DO NOT drift into adjacent columns - stay within vertical boundaries
5. If a cell has multiple activities (e.g., "MAIN POOL - LAP SWIM" and "SMALL POOL - FAMILY SWIM"), extract them as SEPARATE entries""".format(day=day.upper())

    return f"""Extract ALL activities from this pool schedule PDF for {pool_name} for {day.upper()} ONLY.

TASK: Read the schedule and find the {day.upper()} column. Extract EVERY activity from that column ONLY.

{direction_instructions}

For each activity you extract, you MUST include:
- Start time (e.g., "9:00AM")
- End time (e.g., "10:30AM")
- Activity name (e.g., "REC/FAMILY SWIM", "LAP SWIM")
- Pool area if specified (e.g., "Warm Pool", "Shallow Pool", "Deep Pool", "Small Pool", "Main Pool", or lane counts like "(4)" or "(2)"). IMPORTANT: Only include pool_area if it is EXPLICITLY written in the schedule. If no pool area is mentioned, use empty string "".

HANDLING MULTI-ACTIVITY CELLS:
When you see a cell like:
"MAIN POOL - SENIOR/THERAPY SWIM
SMALL POOL - NVPS CLASS
(9:00AM - 10:00AM)
9:00AM - 10:45AM

This means TWO separate activities:
1. SENIOR/THERAPY SWIM in Main Pool from 9:00AM-10:45AM
2. NVPS CLASS in Small Pool from 9:00AM-10:00AM

Extract them as two separate entries.

SHARED TIME SLOT CELLS:
When a cell shows multiple activities at the SAME time like:
"REC/FAMILY SWIM (3 lanes)
Lap Swim (3 Lanes)
6:30-7:30PM"

Extract BOTH as separate entries with the SAME time:
1. REC/FAMILY SWIM with pool_area "(3 lanes)" from 6:30PM-7:30PM
2. LAP SWIM with pool_area "(3 Lanes)" from 6:30PM-7:30PM

IMPORTANT: Make sure to extract the VERY LAST ROW at the bottom of the column - this is commonly missed!

DO NOT filter anything. Extract EVERYTHING including:
- REC/FAMILY SWIM, FAMILY SWIM
- LAP SWIM, LAP SWIMMING
- PARENT CHILD SWIM, PARENT & CHILD SWIM
- YOUTH LESSONS, SWIM LESSONS, LEARN TO SWIM, PARENT CHILD INTRO
- Classes marked with *, **, asterisks
- SENIOR/THERAPY SWIM
- WATER EXERCISE, DEEP WATER EXERCISE
- SWIM TEAM, MASTER'S SWIM TEAM
- Staff meetings, pool closures
- ANY other activity shown

Return in this EXACT JSON format - an array of activities for {day.upper()}:
[
  {{"start": "9:00AM", "end": "10:30AM", "activity": "REC/FAMILY SWIM", "pool_area": "Small Pool"}},
  {{"start": "9:00AM", "end": "10:30AM", "activity": "LAP SWIM", "pool_area": "Main Pool"}},
  ...
]

If no activities for {day.upper()}, return an empty array: []

Return ONLY the JSON array, no other text.

Extract all {day.upper()} activities now."""


def normalize_time(time_str):
    """Normalize time string for comparison (e.g., '9:00AM' -> '09:00AM')."""
    time_str = time_str.upper().strip()
    # Add leading zero if needed
    if time_str[0].isdigit() and (time_str[1] == ':' or time_str[1].isdigit() and time_str[2] == ':'):
        if time_str[1] == ':':
            time_str = '0' + time_str
    return time_str


def get_time_slots(activities):
    """Extract unique time slots (start, end) from activities list."""
    slots = set()
    for act in activities:
        start = normalize_time(act.get('start', ''))
        end = normalize_time(act.get('end', ''))
        if start and end:
            slots.add((start, end))
    return slots


def extract_single_day(pool_name, day, image_data, client):
    """
    Extract activities for a single day using dual extraction (top-down + bottom-up).
    Returns the list of activities for that day, or [] on failure.
    """
    # STEP 1: Top-down extraction
    top_down_prompt = get_extraction_prompt(pool_name, day, "top-down")

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": top_down_prompt
                    }
                ]
            }
        ]
    )

    response_text = parse_json_response(message.content[0].text.strip())

    if not response_text:
        return []

    try:
        top_down_activities = json.loads(response_text)

        # STEP 2: Bottom-up extraction (independent, doesn't see top-down results)
        bottom_up_prompt = get_extraction_prompt(pool_name, day, "bottom-up")

        bottom_up_message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": bottom_up_prompt
                        }
                    ]
                }
            ]
        )

        bottom_up_response = parse_json_response(bottom_up_message.content[0].text.strip())
        bottom_up_activities = json.loads(bottom_up_response) if bottom_up_response else []

        # STEP 3: Compare time slots
        top_down_slots = get_time_slots(top_down_activities)
        bottom_up_slots = get_time_slots(bottom_up_activities)

        if top_down_slots == bottom_up_slots:
            return top_down_activities
        else:
            # Time slots differ - need reconciliation
            # STEP 4: Reconciliation
            reconcile_prompt = f"""I have two different extractions for the {day.upper()} column from this pool schedule. The time slots don't match.

EXTRACTION A (top-down):
{json.dumps(top_down_activities, indent=2)}

EXTRACTION B (bottom-up):
{json.dumps(bottom_up_activities, indent=2)}

Please look at the {day.upper()} column in the image again and determine the CORRECT schedule.

IMPORTANT: If a time slot appears in one extraction but not the other, look at the actual image to verify:
- Does that time range ACTUALLY appear in the {day.upper()} column?
- Look carefully at the times written in the schedule cells
- Is it a real slot or was it hallucinated/misread?

Return the CORRECT and COMPLETE schedule for {day.upper()} based on what you actually see in the image.
Make sure to split multi-activity cells into separate entries.

Return ONLY the JSON array, no explanations."""

            reconcile_message = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": reconcile_prompt
                            }
                        ]
                    }
                ]
            )

            reconcile_response = parse_json_response(reconcile_message.content[0].text.strip())
            try:
                reconciled_activities = json.loads(reconcile_response)
                return reconciled_activities
            except json.JSONDecodeError:
                return top_down_activities

    except json.JSONDecodeError:
        return []


def pick_best_of_three(extractions, day, image_data, client):
    """
    Compare 3 extractions and return the best one.
    - If 2+ match by time slots, return the matching result
    - If all 3 differ, ask Claude to consolidate
    """
    slots = [get_time_slots(e) for e in extractions]

    # Check for matches (majority vote)
    if slots[0] == slots[1]:
        print(f"      ✓ Extractions 1 & 2 match - using extraction 1")
        return extractions[0]
    elif slots[0] == slots[2]:
        print(f"      ✓ Extractions 1 & 3 match - using extraction 1")
        return extractions[0]
    elif slots[1] == slots[2]:
        print(f"      ✓ Extractions 2 & 3 match - using extraction 2")
        return extractions[1]
    else:
        # All 3 differ - ask Claude to consolidate
        print(f"      ⚠ All 3 extractions differ - asking Claude to consolidate")
        print(f"        Slots 1: {slots[0]}")
        print(f"        Slots 2: {slots[1]}")
        print(f"        Slots 3: {slots[2]}")

        consolidate_prompt = f"""I have three different extractions for the {day.upper()} column from this pool schedule. None of them match exactly.

EXTRACTION 1:
{json.dumps(extractions[0], indent=2)}

EXTRACTION 2:
{json.dumps(extractions[1], indent=2)}

EXTRACTION 3:
{json.dumps(extractions[2], indent=2)}

Please look at the {day.upper()} column in the image again and determine the CORRECT schedule.

IMPORTANT:
- Look at the actual image to verify which time slots are real
- If a time slot appears in multiple extractions, it's likely correct
- If a time slot only appears in one extraction, verify it exists in the image
- Don't hallucinate slots that don't exist

Return the CORRECT and COMPLETE schedule for {day.upper()} based on what you actually see in the image.
Make sure to split multi-activity cells into separate entries.

Return ONLY the JSON array, no explanations."""

        consolidate_message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": consolidate_prompt
                        }
                    ]
                }
            ]
        )

        consolidate_response = parse_json_response(consolidate_message.content[0].text.strip())
        try:
            consolidated_activities = json.loads(consolidate_response)
            print(f"      ✓ Consolidated: {len(consolidated_activities)} activities")
            return consolidated_activities
        except json.JSONDecodeError:
            # Fallback to the extraction with the most activities
            print(f"      Warning: Consolidation JSON parse error, using extraction with most activities")
            return max(extractions, key=len)


def extract_raw_schedule(pdf_path, pool_name):
    """
    PASS 1: Extract RAW schedule from PDF by converting to image first.
    Uses best-of-three extraction strategy: runs dual extraction 3 times and picks the best.
    Returns a dict in the format: {weekday: [activity_slots]}
    """
    try:
        # Convert PDF to high-resolution PNG image first
        print(f"  Converting PDF to image for better visual extraction...")
        image_path = convert_pdf_to_image(pdf_path)
        if not image_path:
            print(f"  Failed to convert PDF to image, aborting extraction")
            return None

        # Read the image file and encode it
        with open(image_path, 'rb') as f:
            image_data = base64.standard_b64encode(f.read()).decode('utf-8')

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        raw_schedule = {}

        # Extract each day separately with best-of-three strategy
        for day in weekdays:
            print(f"  Extracting {day} (best of 3)...")

            # Run 3 independent dual extractions
            extractions = []
            for run in range(3):
                print(f"    Run {run + 1}/3...")
                day_result = extract_single_day(pool_name, day, image_data, client)
                extractions.append(day_result)
                print(f"      Got {len(day_result)} activities")

            # Pick the best of three
            raw_schedule[day] = pick_best_of_three(extractions, day, image_data, client)
            print(f"    Final: {len(raw_schedule[day])} activities for {day}")

        print(f"\n✓ Completed best-of-three extraction for all days")
        return raw_schedule

    except Exception as e:
        print(f"Error extracting raw schedule: {e}")
        traceback.print_exc()
        return None


def filter_family_swim(raw_schedule, pool_name):
    """
    PASS 2: Filter raw schedule for family/parent-child swim activities.
    Uses deterministic regex matching (no LLM) to avoid hallucinations.
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    family_swim_data = {
        "Saturday": [], "Sunday": [], "Monday": [],
        "Tuesday": [], "Wednesday": [], "Thursday": [], "Friday": []
    }

    # Patterns to match (case-insensitive)
    family_pattern = re.compile(r'family', re.IGNORECASE)
    parent_child_pattern = re.compile(r'parent.*child', re.IGNORECASE)

    # Patterns to exclude (case-insensitive)
    exclude_pattern = re.compile(r'intro|class|lesson', re.IGNORECASE)

    for day in family_swim_data.keys():
        day_activities = raw_schedule.get(day, [])
        for activity in day_activities:
            activity_name = activity.get("activity", "")
            pool_area = activity.get("pool_area", "")

            # Check if it's a family/parent-child swim
            is_family = family_pattern.search(activity_name)
            is_parent_child = parent_child_pattern.search(activity_name)

            # Check if it should be excluded
            is_excluded = exclude_pattern.search(activity_name)

            if (is_family or is_parent_child) and not is_excluded:
                # Normalize the note
                if is_family:
                    note = "Family Swim"
                else:
                    note = "Parent Child Swim"

                # Add pool area to note if present
                if pool_area and pool_area.strip():
                    area = pool_area.strip()
                    # Clean up area formatting - remove parentheses
                    if area.startswith("(") and area.endswith(")"):
                        area = area[1:-1]
                    # Add area to note if meaningful
                    if area.lower() in ["shallow", "deep"]:
                        note = f"{note} ({area})"
                    elif area and area.lower() not in [""]:
                        note = f"{note} - {area}"

                family_swim_data[day].append({
                    "pool": pool_name,
                    "weekday": day,
                    "start": activity.get("start", ""),
                    "end": activity.get("end", ""),
                    "note": note
                })

    return family_swim_data


def extract_lap_swim_from_raw(raw_schedule, pool_name):
    """
    Extract lap swim activities from raw schedule using Python (no API call).
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    lap_swim_data = {
        "Saturday": [],
        "Sunday": [],
        "Monday": [],
        "Tuesday": [],
        "Wednesday": [],
        "Thursday": [],
        "Friday": []
    }

    for day in lap_swim_data.keys():
        activities = raw_schedule.get(day, [])
        for activity in activities:
            activity_name = activity.get('activity', '').lower()
            if 'lap swim' in activity_name:
                lap_swim_data[day].append({
                    "pool": pool_name,
                    "weekday": day,
                    "start": activity['start'],
                    "end": activity['end'],
                    "note": "Lap Swim"
                })

    return lap_swim_data


def extract_all_activities_from_raw(raw_schedule):
    """
    Extract all NON-lap-swim activities from raw schedule using Python (no API call).
    Used for detecting conflicts with lap swim for secret swim calculation.
    Returns a dict in the format: {weekday: [activity_slots]}
    """
    all_activities_data = {
        "Saturday": [],
        "Sunday": [],
        "Monday": [],
        "Tuesday": [],
        "Wednesday": [],
        "Thursday": [],
        "Friday": []
    }

    for day in all_activities_data.keys():
        activities = raw_schedule.get(day, [])
        for activity in activities:
            activity_name = activity.get('activity', '').lower()
            # Include everything EXCEPT lap swim
            if 'lap swim' not in activity_name:
                all_activities_data[day].append({
                    "start": activity['start'],
                    "end": activity['end'],
                    "activity": activity['activity']
                })

    return all_activities_data


def add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data=None, raw_schedule=None):
    """
    PASS 5: Calculate secret swim times.
    For Garfield Pool: Uses deterministic Python logic (no AI)
    For Balboa Pool: Uses deterministic Python logic (no AI)
    For Hamilton Pool: Uses Claude AI for complex analysis.
    """
    SECRET_SWIM_POOLS = {
        "Balboa Pool": "Parent Child Swim on Steps",
        "Hamilton Pool": "Parent Child Swim in Small Pool",
        "Garfield Pool": "Parent Child Swim in Small Pool"
    }

    if pool_name not in SECRET_SWIM_POOLS:
        return family_swim_data

    secret_swim_note = SECRET_SWIM_POOLS[pool_name]

    # Use deterministic logic for Garfield Pool
    if pool_name == "Garfield Pool" and raw_schedule:
        print(f"  Using deterministic calculation for Garfield secret swim...")
        return calculate_garfield_secret_swim(raw_schedule, pool_name)

    # Use deterministic logic for Hamilton Pool (same logic as Garfield - lane counts indicate main pool)
    if pool_name == "Hamilton Pool" and raw_schedule:
        print(f"  Using deterministic calculation for Hamilton secret swim...")
        return calculate_garfield_secret_swim(raw_schedule, pool_name)

    # Use deterministic logic for Balboa Pool
    if pool_name == "Balboa Pool" and raw_schedule:
        print(f"  Using deterministic calculation for Balboa secret swim...")
        return calculate_balboa_secret_swim(raw_schedule, pool_name)

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        # Prepare the schedule data for Claude
        schedule_data = {
            "all_activities": all_activities_data if all_activities_data else {},
            "family_swim": family_swim_data,
            "lap_swim": lap_swim_data
        }

        # Build pool-specific instructions
        if pool_name == "Hamilton Pool":
            pool_specific_rules = """
HAMILTON POOL SPECIFIC RULES:
- The Small Pool is available for Parent-Child Swim during during other time slots IF it's not being used
- Activities that specify lanes (e.g., "(2)", "(4)", "(6)") are in the MAIN POOL - these do NOT conflict with Small Pool availability for Parent Child Swim in Small Pool
- Activities that specify "Main Pool" do NOT conflict with Small Pool availability
- Activities explicitly mentioning "Small Pool" in the pool location field DO conflict with Parent Child Swim in the Small Pool
- Activities that do not mention a location such as Swim team activities (e.g. Youth Swim Team, Masters Swim Team) and lessons or classes DO conflict Parent Child Swim in Small Pool (they use both pools)
"""
        elif pool_name == "Balboa Pool":
            pool_specific_rules = """
BALBOA POOL SPECIFIC RULES (FOLLOW THESE EXACTLY):
1. Secret swim ("Parent Child Swim on Steps") is ONLY possible during LAP SWIM times
2. For EACH lap swim slot, check ALL activities in "all_activities" for that day
3. A lap swim slot has a CONFLICT if ANY activity in all_activities has a time that:
   - Starts before the lap swim ends, AND
   - Ends after the lap swim starts
   (This catches overlaps, partial overlaps, and activities that contain the lap swim)
4. If a lap swim slot has ANY conflict, do NOT include it as secret swim
5. Only include lap swim slots with ZERO conflicts as secret swim
"""
        elif pool_name == "Garfield Pool":
            pool_specific_rules = """
GARFIELD POOL SPECIFIC RULES:
- The Small Pool is available for Parent-Child Swim during other SCHEDULED activities IF the small pool isn't being used for another activity
- Activities explicitly mentioning "Small Pool" conflict with Parent Child Swim in Small Pool
- Activities in the Small Pool that only partially overlap with a Main Pool activity STILL CONFLICT with Parent Child Swim in Small Pool
- Activities that specify number of Lanes are in the Main Pool and DO NOT conflict with Parent Child Swim in Small Pool
- Activities that do not mention a location such as swim team and lessons (intro/sfusd/etc) use the whole pool, so they conflict
"""
        else:
            pool_specific_rules = ""

        prompt = f"""Analyze this pool schedule and identify "secret swim" times for {pool_name}.

{pool_specific_rules}

GENERAL RULES:
- Secret swim times are opportunistic times when families can use a separate area of the pool DURING the same time as another activity.
- For {pool_name}, secret swim is called: "{secret_swim_note}"
- Secret swim times should be added for time periods when there IS an existing activity but no conflicting activity in the secret swim location.
- there is NEVER secret swim when there is NOT another activity scheduled because the pool won't have life guards.

SCHEDULE DATA:
{json.dumps(schedule_data, indent=2)}

TASK:
For each day of the week, analyze the schedule and determine when secret swim ("{secret_swim_note}") is available.

Return the secret swim times in this exact JSON format:
{{
  "Saturday": [
    {{"pool": "{pool_name}", "weekday": "Saturday", "start": "9:00AM", "end": "12:00PM", "note": "{secret_swim_note}"}},
    ...
  ],
  "Sunday": [...],
  "Monday": [...],
  "Tuesday": [...],
  "Wednesday": [...],
  "Thursday": [...],
  "Friday": [...]
}}

Return ONLY the secret swim slots you've identified (do NOT include the existing family swim data).

Each day should contain only the new secret swim slots. If there aren't any secret swim slots for a day, use an empty array for that day.

Return ONLY the JSON, no other text."""

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Extract JSON
        if '```json' in response_text:
            start = response_text.find('```json') + 7
            end = response_text.find('```', start)
            if end != -1:
                response_text = response_text[start:end].strip()
        elif '```' in response_text:
            start = response_text.find('```') + 3
            end = response_text.rfind('```')
            if end != -1 and end > start:
                response_text = response_text[start:end].strip()
        elif '{' in response_text and '}' in response_text:
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            response_text = response_text[start:end].strip()

        combined_data = json.loads(response_text)
        return combined_data

    except Exception as e:
        print(f"Error calculating secret swim with Claude: {e}")
        traceback.print_exc()
        # Fallback to empty secret swim data
        return {
            "Saturday": [],
            "Sunday": [],
            "Monday": [],
            "Tuesday": [],
            "Wednesday": [],
            "Thursday": [],
            "Friday": []
        }


def combine_and_sort_schedules(family_swim_data, secret_swim_data):
    """
    Combine family swim and secret swim schedules, then sort by start time.
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    combined_data = {}
    weekdays = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    for day in weekdays:
        # Combine family swim and secret swim slots for this day
        day_slots = []
        day_slots.extend(family_swim_data.get(day, []))
        day_slots.extend(secret_swim_data.get(day, []))

        # Sort by start time
        def time_sort_key(slot):
            return time_to_minutes(slot['start'])

        day_slots.sort(key=time_sort_key)
        combined_data[day] = day_slots

    return combined_data


# =============================================================================
# Phantom Entry Detection (Garfield Pool only)
# =============================================================================

WEEKDAY_ORDER = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def get_adjacent_days(day):
    """Return the days before and after the given day."""
    idx = WEEKDAY_ORDER.index(day)
    adjacent = []
    if idx > 0:
        adjacent.append(WEEKDAY_ORDER[idx - 1])
    if idx < len(WEEKDAY_ORDER) - 1:
        adjacent.append(WEEKDAY_ORDER[idx + 1])
    return adjacent


def find_suspicious_duplicates(schedule_data, use_raw_format=False):
    """
    Find slots that have an identical entry on an adjacent day.
    For raw schedule format, compares (start, end, activity, pool_area) case-insensitively.
    For family swim format, compares (start, end, note).
    Returns list of (day, slot, adjacent_day) tuples.
    """
    suspicious = []

    for day, slots in schedule_data.items():
        if day not in WEEKDAY_ORDER:
            continue
        adjacent_days = get_adjacent_days(day)

        for slot in slots:
            if use_raw_format:
                # Case-insensitive comparison for raw format
                slot_key = (
                    slot['start'].upper(),
                    slot['end'].upper(),
                    slot.get('activity', '').upper(),
                    slot.get('pool_area', '').upper()
                )
            else:
                slot_key = (slot['start'], slot['end'], slot['note'])

            for adj_day in adjacent_days:
                adj_slots = schedule_data.get(adj_day, [])
                for adj_slot in adj_slots:
                    if use_raw_format:
                        adj_key = (
                            adj_slot['start'].upper(),
                            adj_slot['end'].upper(),
                            adj_slot.get('activity', '').upper(),
                            adj_slot.get('pool_area', '').upper()
                        )
                    else:
                        adj_key = (adj_slot['start'], adj_slot['end'], adj_slot['note'])
                    if slot_key == adj_key:
                        suspicious.append((day, slot, adj_day))
                        break

    return suspicious


def verify_slot_exists(day, slot, image_path, use_raw_format=False):
    """
    Ask Claude to verify if a specific slot actually exists on the schedule image.
    Returns (is_real, explanation).
    """
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    with open(image_path, 'rb') as f:
        image_data = base64.standard_b64encode(f.read()).decode('utf-8')

    # Get activity description based on format
    if use_raw_format:
        activity_name = slot.get('activity', '')
        pool_area = slot.get('pool_area', '')
        if pool_area:
            activity_desc = f"{activity_name} in {pool_area}"
        else:
            activity_desc = activity_name
    else:
        activity_desc = slot['note']

    prompt = f"""I need you to verify if a specific activity exists on this pool schedule.

QUESTION: Does the {day.upper()} column have a "{activity_desc}" activity from {slot['start']} to {slot['end']}?

IMPORTANT INSTRUCTIONS:
1. Look ONLY at the {day.upper()} column - find the column header that says "{day.upper()}"
2. Draw an imaginary vertical line straight down from that header
3. Look at ONLY the cells in that vertical column
4. Check if there is an activity matching:
   - Time: {slot['start']} to {slot['end']}
   - Activity type: {activity_desc} (or similar wording like REC/FAMILY SWIM, FAMILY SWIM, PARENT CHILD SWIM)

DO NOT look at adjacent columns. The question is ONLY about {day.upper()}.

This is a verification check because the same time slot appears on an adjacent day, and we want to confirm this isn't a column-reading error.

Please respond with EXACTLY one of these formats:
- "YES - [brief reason why you see it]"
- "NO - [brief reason why it's not there]"

Be very careful and look closely at the column boundaries."""

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    )

    response = message.content[0].text.strip()
    response_upper = response.upper()

    # Look for YES or NO in the response
    if "**YES" in response_upper or response_upper.startswith("YES"):
        is_real = True
    elif "**NO" in response_upper or response_upper.startswith("NO"):
        is_real = False
    else:
        # Fallback: look for YES/NO as standalone words
        is_real = " YES " in response_upper or response_upper.startswith("YES")

    return is_real, response


def remove_phantom_entries(schedule_data, image_path, pool_name, use_raw_format=False):
    """
    Detect and remove phantom entries from the schedule.
    A phantom is a slot that appears identically on adjacent days but doesn't
    actually exist (column-reading error during extraction).

    Only runs for Garfield Pool.

    Args:
        schedule_data: The schedule dict (raw or family swim format)
        image_path: Path to the schedule PNG image
        pool_name: Name of the pool
        use_raw_format: If True, uses raw schedule format (activity/pool_area)
                       If False, uses family swim format (note)
    """
    print(f"  Checking for phantom entries (Garfield only)...")

    suspicious = find_suspicious_duplicates(schedule_data, use_raw_format=use_raw_format)

    if not suspicious:
        print(f"    No suspicious duplicates found")
        return schedule_data

    print(f"    Found {len(suspicious)} suspicious entries to verify...")

    # Track which slots we've verified to avoid duplicate API calls
    verified = {}
    phantoms_to_remove = []

    for day, slot, adj_day in suspicious:
        if use_raw_format:
            slot_key = (day, slot['start'], slot['end'], slot.get('activity', ''), slot.get('pool_area', ''))
            slot_desc = f"{slot.get('activity', '')} ({slot.get('pool_area', '')})"
        else:
            slot_key = (day, slot['start'], slot['end'], slot['note'])
            slot_desc = slot['note']

        if slot_key in verified:
            is_real = verified[slot_key]
        else:
            print(f"      Verifying: {day} {slot['start']}-{slot['end']} ({slot_desc})...")
            is_real, explanation = verify_slot_exists(day, slot, image_path, use_raw_format=use_raw_format)
            verified[slot_key] = is_real

            if is_real:
                print(f"        ✓ Confirmed real")
            else:
                print(f"        ✗ Phantom detected: {explanation[:80]}...")

        if not is_real:
            phantoms_to_remove.append((day, slot))

    if not phantoms_to_remove:
        print(f"    All suspicious entries verified as real")
        return schedule_data

    # Remove phantoms from schedule
    print(f"    Removing {len(phantoms_to_remove)} phantom entries...")
    cleaned_data = {}
    for day, slots in schedule_data.items():
        cleaned_slots = []
        for slot in slots:
            if use_raw_format:
                # Case-insensitive comparison for raw format
                is_phantom = any(
                    d == day
                    and s['start'].upper() == slot['start'].upper()
                    and s['end'].upper() == slot['end'].upper()
                    and s.get('activity', '').upper() == slot.get('activity', '').upper()
                    and s.get('pool_area', '').upper() == slot.get('pool_area', '').upper()
                    for d, s in phantoms_to_remove
                )
                slot_desc = f"{slot.get('activity', '')} ({slot.get('pool_area', '')})"
            else:
                is_phantom = any(
                    d == day and s['start'] == slot['start'] and s['end'] == slot['end'] and s['note'] == slot['note']
                    for d, s in phantoms_to_remove
                )
                slot_desc = slot['note']

            if not is_phantom:
                cleaned_slots.append(slot)
            else:
                print(f"      Removed: {day} {slot['start']}-{slot['end']} ({slot_desc})")
        cleaned_data[day] = cleaned_slots

    return cleaned_data


def get_pool_schedule_from_pdf(pool_name, facility_url, current_date, pools_list, pdf_cache_dir="/tmp", force_refresh=False):
    """
    Complete workflow to get pool schedule from PDF using simplified multi-pass strategy.

    Strategy:
    1. Extract RAW schedule from PDF (Claude Sonnet 4.5 - vision only, no filtering)
    2. Filter for family/parent-child swim (Claude Sonnet 4 - JSON filtering, excludes classes like "Parent Child Intro")
    3. Extract lap swim from raw schedule (Python - no API call)
    4. Extract all activities from raw schedule (Python - no API call)
    5. Calculate secret swims (Claude Sonnet 4 - AI analysis with pool-specific rules)
    6. Combine and sort schedules (Python - merge family swim + secret swim, sort by start time)

    Returns a dict in the format: {weekday: [swim_slots]} or None if failed.
    """
    try:
        print(f"\n{'='*60}")
        print(f"Processing {pool_name}")
        print(f"{'='*60}")

        # Step 1: Get documents from facility page
        print(f"Fetching documents from facility page...")
        documents = get_facility_documents(facility_url)
        if not documents:
            print(f"No documents found for {pool_name}")
            return None

        print(f"Found {len(documents)} documents")

        # Build search terms for this pool (same logic as select_schedule_pdf)
        pool_name_lower = pool_name.lower()
        pool_name_base = pool_name_lower.replace(' pool', '')
        pool_name_variants = {
            'martin luther king jr': ['mlk'],
            'mission community': ['mission'],
        }
        search_terms = [pool_name_lower, pool_name_base]
        for key, variants in pool_name_variants.items():
            if key in pool_name_lower:
                search_terms.extend(variants)

        # Get current PDF signature
        current_pdf_signature = get_pdf_list_signature(documents, pool_name, search_terms)
        print(f"  PDF signature: {current_pdf_signature}")

        # Load cache and check if we can use cached data
        cache = load_cache()
        if not force_refresh and pool_name in cache:
            cached_signature = cache[pool_name].get('pdf_signature', [])
            if cached_signature == current_pdf_signature and cache[pool_name].get('schedule_data'):
                print(f"  ✓ PDF list unchanged, using cached schedule data")
                return cache[pool_name]['schedule_data']
            else:
                print(f"  PDF list changed (was: {cached_signature}), re-parsing...")
        elif force_refresh:
            print(f"  Force refresh enabled, re-parsing...")

        # Step 2: Select the appropriate schedule PDF
        selected_pdf = select_schedule_pdf(documents, pool_name, current_date, pools_list)
        if not selected_pdf:
            print(f"No schedule PDF found for {pool_name}")
            # Cache the empty result so we don't keep retrying
            cache[pool_name] = {
                'pdf_signature': current_pdf_signature,
                'schedule_data': None
            }
            save_cache(cache)
            return None

        print(f"Selected: {selected_pdf['name']}")

        # Step 3: Download the PDF
        pdf_path = f"{pdf_cache_dir}/{pool_name.replace(' ', '_')}_schedule.pdf"
        print(f"Downloading PDF...")
        if not download_pdf(selected_pdf['url'], pdf_path):
            print(f"Failed to download PDF for {pool_name}")
            return None

        # PASS 1: Extract raw schedule from PDF (vision only, no filtering)
        print(f"PASS 1: Extracting raw schedule from PDF...")
        raw_schedule = extract_raw_schedule(pdf_path, pool_name)
        if not raw_schedule:
            print(f"Failed to extract raw schedule for {pool_name}")
            return None

        print(f"Raw schedule extracted successfully")

        # Debug: save raw schedule
        debug_path = f"{pdf_cache_dir}/{pool_name.replace(' ', '_')}_raw_schedule.json"
        with open(debug_path, 'w') as f:
            json.dump(raw_schedule, f, indent=2)
        print(f"Saved raw schedule to {debug_path}")

        # PASS 1b: Phantom detection on raw schedule (Garfield only)
        # Must happen before PASS 2+ so secret swim calculations use clean data
        if pool_name == "Garfield Pool":
            image_path = f"{pdf_cache_dir}/{pool_name.replace(' ', '_')}_schedule_page1.png"
            raw_schedule = remove_phantom_entries(raw_schedule, image_path, pool_name, use_raw_format=True)
            # Save cleaned raw schedule
            with open(debug_path, 'w') as f:
                json.dump(raw_schedule, f, indent=2)
            print(f"  Saved cleaned raw schedule to {debug_path}")

        # PASS 2: Filter for family/parent-child swim
        print(f"PASS 2: Filtering for family/parent-child swim...")
        family_swim_data = filter_family_swim(raw_schedule, pool_name)
        if not family_swim_data:
            print(f"Failed to filter family swim for {pool_name}")
            return None

        print(f"Family swim data filtered successfully")

        # For pools with secret swim times, extract lap swim and calculate secret swims
        SECRET_SWIM_POOLS = ["Balboa Pool", "Hamilton Pool", "Garfield Pool"]

        if pool_name in SECRET_SWIM_POOLS:
            # PASS 3: Extract lap swim from raw schedule (Python - no API call)
            print(f"PASS 3: Extracting lap swim from raw schedule...")
            lap_swim_data = extract_lap_swim_from_raw(raw_schedule, pool_name)
            print(f"Found {sum(len(slots) for slots in lap_swim_data.values())} lap swim slots")

            # PASS 4: Extract all non-lap activities from raw schedule (Python - no API call)
            print(f"PASS 4: Extracting all activities for conflict detection...")
            all_activities_data = extract_all_activities_from_raw(raw_schedule)
            print(f"Found {sum(len(slots) for slots in all_activities_data.values())} non-lap activity slots")

            # PASS 5: Calculate secret swims (deterministic for Garfield, AI for others)
            print(f"PASS 5: Calculating secret swim times...")
            secret_swim_data = add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data, raw_schedule)

            # PASS 6: Combine and sort schedules
            print(f"PASS 6: Combining and sorting schedules...")
            combined_data = combine_and_sort_schedules(family_swim_data, secret_swim_data)
        else:
            print(f"Skipping secret swim extraction (not needed for {pool_name})")
            combined_data = family_swim_data

        print(f"✓ Successfully processed {pool_name}")

        # Save to cache
        cache[pool_name] = {
            'pdf_signature': current_pdf_signature,
            'schedule_data': combined_data
        }
        save_cache(cache)

        return combined_data

    except Exception as e:
        print(f"Error processing {pool_name}: {e}")
        traceback.print_exc()
        return None
