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

    for doc in documents:
        doc_name_lower = doc['name'].lower()
        if any(term in doc_name_lower for term in search_terms):
            other_pools = [p.lower() for p in pools_list if p.lower() != pool_name_lower]
            is_other_pool = any(other_pool in doc_name_lower for other_pool in other_pools)

            if not is_other_pool:
                schedule_docs.append(doc)

    if not schedule_docs:
        return None

    if len(schedule_docs) == 1:
        return schedule_docs[0]

    # Use Claude to select the best PDF based on current date
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        doc_list = "\n".join([f"{i+1}. {doc['name']}" for i, doc in enumerate(schedule_docs)])

        prompt = f"""Today's date is {current_date.strftime('%B %d, %Y')} (MM/DD/YYYY: {current_date.strftime('%m/%d/%Y')}).

I have the following pool schedule documents for {pool_name}:

{doc_list}

Which document should I use for today's date? Please respond with ONLY the number (1, 2, 3, etc.) of the best document to use.

Choose the document whose date range includes today's date. If none include today, choose the one with the closest future date range."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )

        response = message.content[0].text.strip()

        try:
            selected_index = int(response) - 1
            if 0 <= selected_index < len(schedule_docs):
                return schedule_docs[selected_index]
        except (ValueError, IndexError):
            pass

    except Exception as e:
        print(f"Warning: Claude selection failed ({e}), falling back to first document")

    return schedule_docs[0]


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


def extract_raw_schedule(pdf_path, pool_name):
    """
    PASS 1: Extract RAW schedule from PDF by converting to image first.
    Pure vision extraction - no filtering, no judgment calls.
    Makes 14 API calls (extract + 1 validation for each of 7 days) to improve accuracy.
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

            prompt = f"""Extract ALL activities from this pool schedule PDF for {pool_name} for {day.upper()} ONLY.

TASK: Read the schedule and find the {day.upper()} column. Extract EVERY activity from that column ONLY.

CRITICAL INSTRUCTIONS FOR READING THE {day.upper()} COLUMN:
⚠️ COMMON ERROR: Accidentally reading activities from adjacent columns. You MUST only include activities that are directly below the column header for {day.upper()} only. Pools are closed some days of the week, so if there is no column header with {day.upper()}, please simply return an empty array.

STEP-BY-STEP PROCESS:
1. Locate the {day.upper()} column header
2. Draw an imaginary vertical line straight down from that header
3. For EACH activity cell in that column:
   a. FIRST: Look up to confirm you're still in the {day.upper()} column - what is the header directly above?
   b. VERIFY: Double-check the column header says {day.upper()}
   c. ONLY THEN: Extract the activity details
4. DO NOT drift into adjacent columns - stay within vertical boundaries
5. If a cell has multiple activities (e.g., "MAIN POOL - LAP SWIM" and "SMALL POOL - FAMILY SWIM"), extract them as SEPARATE entries

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
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            response_text = message.content[0].text.strip()

            # Extract JSON from response
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
            elif '[' in response_text and ']' in response_text:
                start = response_text.find('[')
                end = response_text.rfind(']') + 1
                response_text = response_text[start:end].strip()

            if not response_text:
                print(f"    Warning: Empty response for {day}")
                raw_schedule[day] = []
                continue

            try:
                day_activities = json.loads(response_text)
                print(f"    ✓ Extracted {len(day_activities)} activities for {day}")
                print(f"       V0 (initial): {json.dumps(day_activities, indent=10)}")

                # VALIDATION STEP 1: Immediately validate the extraction
                print(f"  Validation 1 for {day}...")

                validation_prompt = f"""I extracted these activities for {day.upper()} from the pool schedule PDF for {pool_name}:

{json.dumps(day_activities, indent=2)}

STEP-BY-STEP PROCESS FOR VALIDATION:
242 1. Locate the {day.upper()} column header
243 2. Draw an imaginary vertical line straight down from that header
244 3. For EACH activity cell in that column:
245    a. FIRST: Look up to confirm you're still in the {day.upper()} column - what is the header directly above?
246    b. VERIFY: Double-check the column header says {day.upper()}
247    c. ONLY THEN: Extract the activity details
248 4. DO NOT drift into adjacent columns - stay within vertical boundaries
249 5. If a cell has multiple activities (e.g., "MAIN POOL - LAP SWIM" and "SMALL POOL - FAMILY SWIM"), extract them as SEPARATE entries

For each activity, please verify:
1. Are any of these activities actually from a different day (wrong column)?
2. Are the times accurate?
3. Are the pool locations accurate? Please double-check to make sure that the pool location is not combined with the activity name if the activity has a pool location. Also double-check to make sure that if no pool location is specified, we don't have one listed (it should be empty string in this case)
4. Are slots in the schedule where there are two or more activities accurately represented?

For example
MAIN POOL - LAP SWIM
SMALL POOL - WATER EXERCISE
(11:00AM-12:00PM)
11:00AM-1:00PM

should be two activities:
A. LAP SWIM in the Main Pool from 11:00AM-1:00PM
B. WATER EXERCISE in the Small Pool from 11:00AM-12:00PM

another example
MAIN POOL - SEHIOR/THERAPY SWIM
SMALL POOL - SWIM LESSONS
9:00AM - 10:45AM

should be two activities:
A. SEHIOR/THERAPY SWIM in the Main Pool from 9:00AM-10:45AM
B. SWIM LESSONS in the Small Pool from 9:00AM-10:45AM

Based on the two examples, you need to CAREFULLY DIFFERENTIATE the case where two items in the same slot share the same time or if one item has a subtimeslot inside the larger time slot.

When you check this MAKE SURE that you are looking at the correct {day.upper()} column and not at the column on either side.

Please double-check the {day.upper()} column in the PDF and return the CORRECT JSON with any necessary changes.

Return ONLY the corrected JSON array in this exact format:
[
  {{"start": "9:00AM", "end": "10:30AM", "activity": "REC/FAMILY SWIM", "pool_area": "Small Pool"}},
  ...
]

Note that it's possible {day.upper()} is not in the schedule at all. In this case just return an empty array.

If the extraction was already correct, return it unchanged. Return ONLY the JSON array, no explanations."""

                validation_message = client.messages.create(
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
                                    "text": validation_prompt
                                }
                            ]
                        }
                    ]
                )

                validation_response = validation_message.content[0].text.strip()

                # Extract JSON from validation response
                if '```json' in validation_response:
                    start = validation_response.find('```json') + 7
                    end = validation_response.find('```', start)
                    if end != -1:
                        validation_response = validation_response[start:end].strip()
                elif '```' in validation_response:
                    start = validation_response.find('```') + 3
                    end = validation_response.rfind('```')
                    if end != -1 and end > start:
                        validation_response = validation_response[start:end].strip()
                elif '[' in validation_response and ']' in validation_response:
                    start = validation_response.find('[')
                    end = validation_response.rfind(']') + 1
                    validation_response = validation_response[start:end].strip()

                try:
                    validated_activities_v1 = json.loads(validation_response)

                    # Check if validation made changes
                    if validated_activities_v1 != day_activities:
                        print(f"    ⚠ Validation 1 made changes: {len(day_activities)} -> {len(validated_activities_v1)} activities")
                        print(f"       V1 (after val 1): {json.dumps(validated_activities_v1, indent=10)}")
                    else:
                        print(f"    ✓ Validation 1: No changes needed")

                    raw_schedule[day] = validated_activities_v1
                except json.JSONDecodeError as e:
                    print(f"    Warning: Validation 1 JSON parse error for {day}, using original extraction")
                    raw_schedule[day] = day_activities

            except json.JSONDecodeError as e:
                print(f"    Error parsing JSON for {day}: {e}")
                print(f"    Response (first 200 chars): {response_text[:200]}")
                raw_schedule[day] = []

        print(f"\n✓ Completed extraction and 1 validation pass for all days")
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


def add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data=None):
    """
    PASS 5: Calculate secret swim times using Claude AI.
    Add "secret swim" times based on lap swim availability.
    For Balboa Pool: Add "Parent Child Swim on Steps" during lap swim when no other activity
    For Hamilton Pool: Add "Parent Child Swim in Small Pool" during lap swim when no other activity
    For Garfield Pool: Add "Parent Child Swim in Small Pool" during lap swim when no other activity
    """
    SECRET_SWIM_POOLS = {
        "Balboa Pool": "Parent Child Swim on Steps",
        "Hamilton Pool": "Parent Child Swim in Small Pool",
        "Garfield Pool": "Parent Child Swim in Small Pool"
    }

    if pool_name not in SECRET_SWIM_POOLS:
        return family_swim_data

    secret_swim_note = SECRET_SWIM_POOLS[pool_name]

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
- Activities that specify lanes (e.g., "(2)", "(4)", "(6)") are in the MAIN POOL - these do NOT conflict with Small Pool availability
- Activities that specify "Main Pool" do NOT conflict with Small Pool availability
- Activities explicitly mentioning "Small Pool" in the pool location field DO conflict with Parent Child Swim in the Small Pool
- Activities that do not mention a location such as Swim team activities and lessons or classes DO conflict Parent Child Swim in the Small Pool (they use both pools)
"""
        elif pool_name == "Balboa Pool":
            pool_specific_rules = """
BALBOA POOL SPECIFIC RULES:
- The Steps area is available for Parent-Child Swim during lap swim times IF there is no other conflicting activity
- Any activity that overlaps with lap swim time creates a conflict (except lap swim itself)
- Parent-Child Swim on Steps is NOT available during any activity that is NOT lap swim specifically
"""
        elif pool_name == "Garfield Pool":
            pool_specific_rules = """
GARFIELD POOL SPECIFIC RULES:
- The Small Pool is available for Parent-Child Swim during lap swim times when the small pool isn't being used
- Activities explicitly mentioning "Small Pool" conflict
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
            model="claude-sonnet-4-20250514",
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

            # PASS 5: Calculate secret swims using Claude AI
            print(f"PASS 5: Calculating secret swim times with Claude...")
            secret_swim_data = add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data)

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
