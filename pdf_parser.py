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
from bs4 import BeautifulSoup
from anthropic import Anthropic
from constants import ANTHROPIC_API_KEY
import pypdfium2 as pdfium


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

Reply with just the number or NONE."""

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
                print(f"  Warning: Claude returned index {selected_index + 1} but only {len(schedule_docs)} candidates")

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


def extract_raw_schedule(pdf_path, pool_name):
    """
    PASS 1: Extract RAW schedule from PDF by converting to image first.
    Uses dual extraction (top-down + bottom-up) with reconciliation for accuracy.
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

        # Extract each day separately with individual API calls
        for day in weekdays:
            print(f"  Extracting {day}...")

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
                print(f"    Warning: Empty response for {day}")
                raw_schedule[day] = []
                continue

            try:
                top_down_activities = json.loads(response_text)
                print(f"    ✓ Top-down: {len(top_down_activities)} activities")

                # STEP 2: Bottom-up extraction (independent, doesn't see top-down results)
                print(f"    Running bottom-up extraction...")
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
                print(f"    ✓ Bottom-up: {len(bottom_up_activities)} activities")

                # STEP 3: Compare time slots
                top_down_slots = get_time_slots(top_down_activities)
                bottom_up_slots = get_time_slots(bottom_up_activities)

                if top_down_slots == bottom_up_slots:
                    print(f"    ✓ Time slots match - using top-down extraction")
                    raw_schedule[day] = top_down_activities
                else:
                    # Time slots differ - need reconciliation
                    only_in_top_down = top_down_slots - bottom_up_slots
                    only_in_bottom_up = bottom_up_slots - top_down_slots
                    print(f"    ⚠ Time slots DIFFER:")
                    if only_in_top_down:
                        print(f"       Only in top-down: {only_in_top_down}")
                    if only_in_bottom_up:
                        print(f"       Only in bottom-up: {only_in_bottom_up}")

                    # STEP 4: Reconciliation
                    print(f"    Running reconciliation...")
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
                        print(f"    ✓ Reconciled: {len(reconciled_activities)} activities")
                        raw_schedule[day] = reconciled_activities
                    except json.JSONDecodeError:
                        print(f"    Warning: Reconciliation JSON parse error, using top-down")
                        raw_schedule[day] = top_down_activities

            except json.JSONDecodeError as e:
                print(f"    Error parsing JSON for {day}: {e}")
                print(f"    Response (first 200 chars): {response_text[:200]}")
                raw_schedule[day] = []

        print(f"\n✓ Completed dual extraction for all days")
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


def get_pool_schedule_from_pdf(pool_name, facility_url, current_date, pools_list, pdf_cache_dir="/tmp"):
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

        # Step 2: Select the appropriate schedule PDF
        selected_pdf = select_schedule_pdf(documents, pool_name, current_date, pools_list)
        if not selected_pdf:
            print(f"No schedule PDF found for {pool_name}")
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
        return combined_data

    except Exception as e:
        print(f"Error processing {pool_name}: {e}")
        traceback.print_exc()
        return None
