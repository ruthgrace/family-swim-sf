"""
PDF parsing utilities for extracting pool schedules

Simplified Multi-Pass Strategy:
1. Extract RAW schedule from PDF (Claude Opus - vision only, no filtering)
2. Filter for family/parent-child swim (Claude Haiku - JSON filtering)
3. Extract lap swim from raw schedule (Python - no API call)
4. Extract all activities from raw schedule (Python - no API call)
5. Calculate secret swims (Python logic)

This approach minimizes API calls and separates vision tasks from filtering logic.
"""

import requests
import traceback
import json
import base64
from bs4 import BeautifulSoup
from anthropic import Anthropic
from constants import ANTHROPIC_API_KEY


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
    PASS 1: Extract RAW schedule from PDF.
    Pure vision extraction - no filtering, no judgment calls.
    Makes 7 separate API calls (one per day) to improve accuracy.
    Returns a dict in the format: {weekday: [activity_slots]}
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')

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
- Pool area if specified (e.g., "Warm Pool", "Shallow Pool", "Deep Pool", "Small Pool", "Main Pool", or lane counts like "(4)" or "(2)"). If not specified, use empty string.

HANDLING MULTI-ACTIVITY CELLS:
When you see a cell like:
"MAIN POOL - SENIOR/THERAPY SWIM
SMALL POOL - NVPS CLASS
(9:00AM - 10:00AM)
9:00AM - 10:45AM"

This means TWO separate activities:
1. SENIOR/THERAPY SWIM in Main Pool from 9:00AM-10:45AM
2. NVPS CLASS in Small Pool from 9:00AM-10:00AM

Extract them as two separate entries.

DO NOT filter anything. Extract EVERYTHING including:
- REC/FAMILY SWIM, FAMILY SWIM
- LAP SWIM, LAP SWIMMING
- PARENT CHILD SWIM, PARENT & CHILD SWIM
- YOUTH LESSONS, SWIM LESSONS, LEARN TO SWIM
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
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_data
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
                raw_schedule[day] = day_activities
                print(f"    ✓ Extracted {len(day_activities)} activities for {day}")
            except json.JSONDecodeError as e:
                print(f"    Error parsing JSON for {day}: {e}")
                print(f"    Response (first 200 chars): {response_text[:200]}")
                raw_schedule[day] = []

        print(f"\n✓ Completed extraction for all days")
        return raw_schedule

    except Exception as e:
        print(f"Error extracting raw schedule: {e}")
        traceback.print_exc()
        return None


def filter_family_swim(raw_schedule, pool_name):
    """
    PASS 2: Filter raw schedule for family/parent-child swim activities.
    Works on JSON data (no PDF vision needed).
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        raw_schedule_json = json.dumps(raw_schedule, indent=2)

        prompt = f"""Given this pool schedule JSON, extract ONLY the family swim and parent-child swim activities.

INCLUDE activities that are:
- "REC/FAMILY SWIM", "FAMILY SWIM"
- "PARENT CHILD SWIM", "PARENT & CHILD SWIM", "PARENT AND CHILD SWIM", "PARENT/CHILD SWIM" etc.

EXCLUDE activities with:
- "LESSON", "INTRO", "CLASS", "LEARN TO", "INSTRUCTION"
- "SENIOR", "THERAPY", "YOUTH LESSONS", "SWIM TEAM", "MASTER'S"
- "WATER EXERCISE", "DEEP WATER EXERCISE"
- "LAP SWIM" (unless it explicitly says "REC/FAMILY" or something else indicating family swim or parent/child swim in the same activity name)

Input schedule:
{raw_schedule_json}

Return filtered schedule in this format:
{{
  "FAMILY_SWIM": {{
    "Saturday": [
      {{"pool": "{pool_name}", "weekday": "Saturday", "start": "9:00AM", "end": "10:30AM", "note": "Family Swim"}},
      ...
    ],
    "Sunday": [...],
    ...
  }},
  "PARENT CHILD SWIM": {{
    "Saturday": [
      {{"pool": "{pool_name}", "weekday": "Saturday", "start": "9:00AM", "end": "10:30AM", "note": "Parent Child Swim"}},
      ...
    ],
    "Sunday": [...],
    ...
  }}
}}

Please include all days of the week. If there aren't any relevant activities for that day, it can be an empty array.

Use the "note" field if a specific location is specified, e.g. "Small pool".

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

        family_swim_data = json.loads(response_text)

        # Merge the two categories into a single flat structure
        merged_data = {
            "Saturday": [],
            "Sunday": [],
            "Monday": [],
            "Tuesday": [],
            "Wednesday": [],
            "Thursday": [],
            "Friday": []
        }

        # Add family swim slots
        if "FAMILY_SWIM" in family_swim_data:
            for day in merged_data.keys():
                merged_data[day].extend(family_swim_data["FAMILY_SWIM"].get(day, []))

        # Add parent-child swim slots
        if "PARENT CHILD SWIM" in family_swim_data:
            for day in merged_data.keys():
                merged_data[day].extend(family_swim_data["PARENT CHILD SWIM"].get(day, []))

        return merged_data

    except Exception as e:
        print(f"Error filtering family swim: {e}")
        traceback.print_exc()
        return None


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
    PASS 5: Calculate secret swim times (Python logic).
    Add "secret swim" times based on lap swim availability.
    For Balboa Pool: Add "Parent Child Swim on Steps" during lap swim when no other activity
    For Hamilton Pool: Add "Family Swim in Small Pool" during lap swim when no other activity
    For Garfield Pool: Add "Parent Child Swim in Small Pool" during lap swim when no other activity
    """
    SECRET_SWIM_POOLS = {
        "Balboa Pool": "Parent Child Swim on Steps",
        "Hamilton Pool": "Family Swim in Small Pool",
        "Garfield Pool": "Parent Child Swim in Small Pool"
    }

    if pool_name not in SECRET_SWIM_POOLS:
        return family_swim_data

    secret_swim_note = SECRET_SWIM_POOLS[pool_name]
    combined_data = {}

    weekdays = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    for day in weekdays:
        combined_data[day] = list(family_swim_data.get(day, []))
        lap_slots = lap_swim_data.get(day, [])

        for lap_slot in lap_slots:
            lap_start = time_to_minutes(lap_slot['start'])
            lap_end = time_to_minutes(lap_slot['end'])

            conflicts = []

            # Check conflicts with ALL activities if we have that data
            if all_activities_data:
                all_activities = all_activities_data.get(day, [])
                for activity in all_activities:
                    # Skip lap swim itself
                    if 'lap swim' in activity.get('activity', '').lower():
                        continue

                    activity_start = time_to_minutes(activity['start'])
                    activity_end = time_to_minutes(activity['end'])

                    # Check for time overlap
                    if not (lap_end <= activity_start or lap_start >= activity_end):
                        conflicts.append((activity_start, activity_end))
            else:
                # Fallback: only check family swim conflicts
                family_slots = family_swim_data.get(day, [])
                for family_slot in family_slots:
                    family_start = time_to_minutes(family_slot['start'])
                    family_end = time_to_minutes(family_slot['end'])

                    if not (lap_end <= family_start or lap_start >= family_end):
                        conflicts.append((family_start, family_end))

            if not conflicts:
                # No conflicts - add the full lap swim time as secret swim
                combined_data[day].append({
                    "pool": pool_name,
                    "weekday": day,
                    "start": lap_slot['start'],
                    "end": lap_slot['end'],
                    "note": secret_swim_note
                })
            else:
                # There are conflicts - find available time ranges within the lap swim period
                conflicts.sort()
                available_ranges = []
                current_start = lap_start

                for conflict_start, conflict_end in conflicts:
                    if current_start < conflict_start:
                        available_ranges.append((current_start, conflict_start))
                    current_start = max(current_start, conflict_end)

                if current_start < lap_end:
                    available_ranges.append((current_start, lap_end))

                # Add secret swim times for available ranges
                for start_min, end_min in available_ranges:
                    combined_data[day].append({
                        "pool": pool_name,
                        "weekday": day,
                        "start": minutes_to_time(start_min),
                        "end": minutes_to_time(end_min),
                        "note": secret_swim_note
                    })

    return combined_data


def get_pool_schedule_from_pdf(pool_name, facility_url, current_date, pools_list, pdf_cache_dir="/tmp"):
    """
    Complete workflow to get pool schedule from PDF using simplified multi-pass strategy.

    Strategy:
    1. Extract RAW schedule from PDF (Claude Opus - vision only)
    2. Filter for family/parent-child swim (Claude Haiku - JSON filtering)
    3. Extract lap swim from raw schedule (Python - no API call)
    4. Extract all activities from raw schedule (Python - no API call)
    5. Calculate secret swims (Python logic)

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

            # PASS 5: Calculate secret swims (Python logic)
            print(f"PASS 5: Calculating secret swim times...")
            combined_data = add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data)
        else:
            print(f"Skipping secret swim extraction (not needed for {pool_name})")
            combined_data = family_swim_data

        print(f"✓ Successfully processed {pool_name}")
        return combined_data

    except Exception as e:
        print(f"Error processing {pool_name}: {e}")
        traceback.print_exc()
        return None
