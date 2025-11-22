"""
PDF parsing utilities for extracting pool schedules
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
    import json
    from anthropic import Anthropic

    schedule_docs = []
    pool_name_lower = pool_name.lower()
    # Extract the pool name without "Pool" suffix for matching
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
        # Look for documents that contain the pool name or any variant
        if any(term in doc_name_lower for term in search_terms):
            other_pools = [p.lower() for p in pools_list if p.lower() != pool_name_lower]
            is_other_pool = any(other_pool in doc_name_lower for other_pool in other_pools)

            if not is_other_pool:
                schedule_docs.append(doc)

    # No fallback - if we don't find a pool-specific PDF, assume the pool has no schedule
    # This prevents using the wrong pool's schedule (e.g., Mission Pool Schedule for Rossi Pool)
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

        # Extract the number from the response
        try:
            selected_index = int(response) - 1
            if 0 <= selected_index < len(schedule_docs):
                return schedule_docs[selected_index]
        except (ValueError, IndexError):
            pass

    except Exception as e:
        print(f"Warning: Claude selection failed ({e}), falling back to first document")

    # Fallback to first document if Claude selection fails
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


def add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data=None):
    """
    Add "secret swim" times based on lap swim availability.
    For Balboa Pool: Add "Parent Child Swim on Steps" during lap swim when no other activity
    For Hamilton Pool: Add "Family Swim in Small Pool" during lap swim when no other activity
    For Garfield Pool: Add "Parent Child Swim in Small Pool" during lap swim when no other activity

    Now checks against ALL activities (including classes/lessons) to ensure secret swim is only
    added when the pool area is truly available for drop-in use.
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
                # Fallback to old logic: only check family swim conflicts
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


def extract_lap_swim_times(pdf_path, pool_name):
    """
    Use Claude to extract lap swim times from the pool schedule PDF.
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""Please analyze this pool schedule PDF for {pool_name} and extract ONLY the Lap Swim times.

CRITICAL: This schedule is a multi-column table with days across the top.
Before recording ANY time slot, you MUST:
1. Locate the day column header (TUESDAY, WEDNESDAY, THURSDAY, etc.)
2. Trace straight down that specific column to find times
3. Do NOT accidentally shift to adjacent columns - this is a common error
4. Double-check that each time belongs to the correct day

IMPORTANT: Only include times that are specifically labeled as "Lap Swim". Be very careful to:
- Look at the correct day column
- Do NOT mix up days (e.g., don't put Thursday times into Friday)
- Do NOT include any other activities like classes, lessons, or other swim programs
- Be especially careful with morning times (7:00AM-8:00AM) which may appear on multiple days

DISTINGUISHING LAP SWIM FROM CLASSES (VERY IMPORTANT):
- ONLY extract time slots that are explicitly labeled as "LAP SWIM" or "LAP SWIMMING"
- DO NOT include if there are ANY paid classes happening at the same time, even if lap swim is also listed
- Look for registration indicators: **, asterisks, "pre-registration required", "registration"
- Activity names with "INTRO", "LESSON", "LEARN TO", "CLASS", "INSTRUCTION" indicate PAID CLASSES
- Examples of what to SKIP: "LEARN TO SWIM", "SWIM LESSONS", "SWIM INSTRUCTION", "PARENT/CHILD INTRO"
- If a time slot shows "LAP SWIM" AND a class/lesson simultaneously (even in different pool areas), DO NOT include it
- This is because classes in other pool areas prevent family members from using the lap swim area for drop-in

I need the data in this exact JSON format:
{{
    "Saturday": [
        {{"pool": "{pool_name}", "weekday": "Saturday", "start": "7:00AM", "end": "11:00AM", "note": "Lap Swim"}},
        ...
    ],
    "Sunday": [...],
    "Monday": [...],
    "Tuesday": [...],
    "Wednesday": [...],
    "Thursday": [...],
    "Friday": [...]
}}

Important formatting rules:
1. Times must be formatted like "9:00AM" or "2:30PM" (no space between time and AM/PM)
2. Use full weekday names: Saturday, Sunday, Monday, Tuesday, Wednesday, Thursday, Friday
3. The "note" field should always be "Lap Swim"
4. If no lap swim is scheduled for a day, use an empty array []
5. ONLY include times specifically labeled as "Lap Swim" where NO classes or lessons are occurring simultaneously
6. Double-check that you have the correct day for each time slot
7. Return ONLY the JSON, no other text

Please carefully extract all lap swim times from this schedule."""

        message = client.messages.create(
            model="claude-opus-4-1-20250805",
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

        # Extract JSON from response - Claude may add explanatory text
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
            # Extract just the JSON object
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            response_text = response_text[start:end].strip()

        if not response_text:
            print(f"Warning: Empty response from Claude for lap swim extraction")
            print(f"Raw response: {message.content[0].text[:200]}")
            return None

        lap_swim_data = json.loads(response_text)
        return lap_swim_data

    except json.JSONDecodeError as e:
        print(f"Error parsing lap swim JSON: {e}")
        print(f"Response text (first 500 chars): {response_text[:500]}")
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"Error extracting lap swim times with Claude: {e}")
        traceback.print_exc()
        return None


def extract_all_activities(pdf_path, pool_name):
    """
    Extract ALL activities/time slots from the schedule (including classes, lessons, etc.).
    This is used to detect conflicts with lap swim times for secret swim calculation.
    Returns a dict in the format: {weekday: [activity_slots]}
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""Please analyze this pool schedule PDF for {pool_name} and extract ALL activities and time slots.

CRITICAL: This schedule is a multi-column table with days across the top.
Before recording ANY time slot, you MUST:
1. Locate the day column header (TUESDAY, WEDNESDAY, THURSDAY, etc.)
2. Trace straight down that specific column to find times
3. Do NOT accidentally shift to adjacent columns - this is a common error
4. Double-check that each time belongs to the correct day

IMPORTANT: Extract EVERY activity shown in the schedule, including:
- Lap Swim
- Family Swim / REC/FAMILY SWIM
- Parent & Child Swim
- Learn to Swim / Swim Lessons
- Classes with **, asterisks, or registration markers
- Senior activities, therapy swim
- Youth programs
- ANY other scheduled activity

The goal is to capture EVERYTHING that's happening at the pool so we can identify all time slots that are occupied.

Return the data in this exact JSON format:
{{
    "Saturday": [
        {{"start": "9:00AM", "end": "10:30AM", "activity": "Lap Swim"}},
        {{"start": "9:00AM", "end": "11:00AM", "activity": "Learn to Swim"}},
        ...
    ],
    "Sunday": [...],
    "Monday": [...],
    "Tuesday": [...],
    "Wednesday": [...],
    "Thursday": [...],
    "Friday": [...]
}}

Important formatting rules:
1. Times must be formatted like "9:00AM" or "2:30PM" (no space between time and AM/PM)
2. Use full weekday names: Saturday, Sunday, Monday, Tuesday, Wednesday, Thursday, Friday
3. The "activity" field should be a brief description of what's happening
4. If no activities are scheduled for a day, use an empty array []
5. Include ALL activities - don't filter anything out
6. If activities happen simultaneously, list them both
7. Return ONLY the JSON, no other text

Please carefully extract all activities from this schedule."""

        message = client.messages.create(
            model="claude-opus-4-1-20250805",
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

        # Extract JSON from response - Claude may add explanatory text
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
            # Extract just the JSON object
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            response_text = response_text[start:end].strip()

        if not response_text:
            print(f"Warning: Empty response from Claude for all activities extraction")
            return None

        all_activities = json.loads(response_text)
        return all_activities

    except json.JSONDecodeError as e:
        print(f"Error parsing all activities JSON: {e}")
        print(f"Response text (first 500 chars): {response_text[:500]}")
        return None
    except Exception as e:
        print(f"Error extracting all activities with Claude: {e}")
        traceback.print_exc()
        return None


def extract_single_day_schedule(pdf_path, pool_name, weekday):
    """
    Extract schedule for a single specific day from the PDF.
    This reduces column confusion by focusing Claude on one day at a time.
    Returns a list of swim slots for that day.
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""Please analyze this pool schedule PDF for {pool_name}.

TASK: Extract ONLY the schedule for {weekday.upper()}.

CRITICAL INSTRUCTIONS:
1. This is a multi-column table with days of the week as column headers
2. Find the column header for {weekday.upper()}
3. Read ONLY the times directly under that {weekday.upper()} column
4. Do NOT accidentally read times from adjacent columns (this is very important!)
5. Trace straight down the {weekday.upper()} column to extract all time slots

For {weekday}, please identify all activities that are:
- Family Swim or REC/FAMILY SWIM
- Parent & Child Swim or Parent Child Swim
- Any variant with "family" or "parent child" for drop-in/open swim

DISTINGUISHING FREE SWIM FROM PAID CLASSES (VERY IMPORTANT):
- Look for registration indicators: **, asterisks, "pre-registration required", "registration"
- Activity names with "INTRO", "LESSON", "LEARN TO", "CLASS", "INSTRUCTION" are typically PAID CLASSES, NOT free swim
- Examples of FREE swim: "PARENT/CHILD SWIM", "FAMILY SWIM", "REC/FAMILY SWIM", "PARENT & CHILD SWIM"
- Examples of PAID classes to SKIP: "PARENT/CHILD INTRO", "LEARN TO SWIM", "SWIM LESSONS", "SWIM INSTRUCTION"
- Multiple activities can occur simultaneously in different pool areas - extract ONLY the free drop-in swim activities
- If an activity has markers indicating pre-registration (like ** or asterisks) or is labeled as a class/lesson/intro, SKIP IT COMPLETELY

Do NOT include:
- Lap swim (unless it explicitly says "REC/FAMILY" or "parent child")
- Any activities with "INTRO", "LESSON", "LEARN TO", "CLASS", "INSTRUCTION" in the name
- Activities marked with **, asterisks, or registration requirements
- Senior activities, therapy swim, or guided exercise
- Youth programs, synchro, or other structured activities

Return the data in this JSON format:
{{
    "day": "{weekday}",
    "slots": [
        {{"start": "1:30PM", "end": "2:30PM", "activity": "REC/FAMILY SWIM"}},
        ...
    ]
}}

Important:
- Times must be formatted like "9:00AM" or "2:30PM" (no space between time and AM/PM)
- If no family swim is scheduled for {weekday}, return an empty slots array
- Return ONLY the JSON, no other text
- Double-check you're reading from the {weekday.upper()} column, not an adjacent day

Please carefully extract {weekday}'s schedule."""

        message = client.messages.create(
            model="claude-opus-4-1-20250805",
            max_tokens=2048,
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

        # Extract JSON from response (Claude might add explanatory text)
        # Look for JSON content between ```json and ``` or just find the first { to last }
        if '```json' in response_text:
            start = response_text.find('```json') + 7
            end = response_text.find('```', start)
            response_text = response_text[start:end].strip()
        elif '```' in response_text:
            start = response_text.find('```') + 3
            end = response_text.rfind('```')
            response_text = response_text[start:end].strip()
        elif '{' in response_text and '}' in response_text:
            # Extract just the JSON object
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            response_text = response_text[start:end].strip()

        day_data = json.loads(response_text)

        # Convert to our standard format
        slots = []
        for slot in day_data.get('slots', []):
            activity = slot.get('activity', '').lower()

            # Determine note based on activity text
            if 'parent' in activity and 'child' in activity:
                if 'small pool' in activity:
                    note = "Parent Child Swim in Small Pool"
                elif 'steps' in activity:
                    note = "Parent Child Swim on Steps"
                else:
                    note = "Parent Child Swim"
            elif 'small pool' in activity:
                note = "Family Swim in Small Pool"
            else:
                note = "Family Swim"

            slots.append({
                "pool": pool_name,
                "weekday": weekday,
                "start": slot['start'],
                "end": slot['end'],
                "note": note
            })

        return slots

    except Exception as e:
        print(f"Error extracting {weekday} schedule: {e}")
        traceback.print_exc()
        return []


def extract_family_swim_day_by_day(pdf_path, pool_name):
    """
    Extract family swim schedule by processing one day at a time.
    This should reduce column confusion errors.
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    try:
        schedule_data = {
            "Saturday": [],
            "Sunday": [],
            "Monday": [],
            "Tuesday": [],
            "Wednesday": [],
            "Thursday": [],
            "Friday": []
        }

        for day in ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Monday"]:
            print(f"  Extracting {day}...")
            slots = extract_single_day_schedule(pdf_path, pool_name, day)
            schedule_data[day] = slots

        return schedule_data

    except Exception as e:
        print(f"Error in day-by-day extraction: {e}")
        traceback.print_exc()
        return None


def pdf_table_to_markdown(pdf_path, pool_name):
    """
    First pass: Ask Claude to convert the schedule table to markdown.
    This helps us see what Claude is reading before trying to parse it.
    Returns markdown string representation of the schedule table.
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""Please analyze this pool schedule PDF for {pool_name}.

I need you to convert the main schedule table into a clear markdown table format.

CRITICAL INSTRUCTIONS:
1. This is a multi-column table with days of the week as column headers
2. Each column represents ONE day (Tuesday, Wednesday, Thursday, Friday, Saturday, etc.)
3. You MUST carefully trace down each column to get the correct times for that day
4. DO NOT mix up columns - verify each time slot is under the correct day header

Please create a markdown table with these columns:
| Day | Time | Activity |

For each row, extract:
- Day: The day of the week (Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday, Monday)
- Time: The time range (e.g., "1:30 pm - 2:30 pm")
- Activity: The activity name (e.g., "REC/FAMILY SWIM", "LAP SWIM", "PARENT & CHILD FAMILY SWIM")

IMPORTANT:
- Include ALL activities (family swim, lap swim, lessons, etc.) - we'll filter later
- Be extremely careful to match times to the correct day column
- If unsure about which column a time belongs to, note it in the activity field
- Return ONLY the markdown table, no other text

Please carefully read the schedule table and convert it to markdown."""

        message = client.messages.create(
            model="claude-opus-4-1-20250805",
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

        markdown_text = message.content[0].text.strip()

        # Remove markdown code blocks if present
        if markdown_text.startswith('```markdown'):
            markdown_text = markdown_text[11:]
        if markdown_text.startswith('```'):
            markdown_text = markdown_text[3:]
        if markdown_text.endswith('```'):
            markdown_text = markdown_text[:-3]
        markdown_text = markdown_text.strip()

        return markdown_text

    except Exception as e:
        print(f"Error converting PDF to markdown: {e}")
        traceback.print_exc()
        return None


def parse_markdown_schedule(markdown_text, pool_name):
    """
    Parse the markdown table into schedule data.
    This uses Python string parsing instead of relying on Claude to extract correctly.
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    try:
        schedule_data = {
            "Saturday": [],
            "Sunday": [],
            "Monday": [],
            "Tuesday": [],
            "Wednesday": [],
            "Thursday": [],
            "Friday": []
        }

        # Activity patterns to look for (family swim related)
        family_patterns = [
            'family swim',
            'rec/family',
            'parent & child',
            'parent child',
            'parent and child'
        ]

        lines = markdown_text.strip().split('\n')

        for line in lines:
            # Skip header and separator lines
            if '|' not in line or '---' in line or 'Day' in line or 'TIME' in line:
                continue

            # Parse table row: | Day | Time | Activity |
            parts = [p.strip() for p in line.split('|')]
            # Remove empty first/last elements from split
            parts = [p for p in parts if p]

            if len(parts) < 3:
                continue

            day = parts[0].strip()
            time_range = parts[1].strip()
            activity = parts[2].strip().lower()

            # Check if this is a family swim activity
            is_family_swim = any(pattern in activity for pattern in family_patterns)

            if not is_family_swim:
                continue

            # Parse time range (e.g., "1:30 pm - 2:30 pm")
            try:
                time_parts = time_range.split('-')
                if len(time_parts) != 2:
                    continue

                start_time = time_parts[0].strip().upper().replace(' ', '')
                end_time = time_parts[1].strip().upper().replace(' ', '')

                # Determine note based on activity text
                if 'parent' in activity and 'child' in activity:
                    if 'small pool' in activity:
                        note = "Parent Child Swim in Small Pool"
                    elif 'steps' in activity:
                        note = "Parent Child Swim on Steps"
                    else:
                        note = "Parent Child Swim"
                elif 'small pool' in activity:
                    note = "Family Swim in Small Pool"
                else:
                    note = "Family Swim"

                # Validate day is in our schedule
                if day in schedule_data:
                    schedule_data[day].append({
                        "pool": pool_name,
                        "weekday": day,
                        "start": start_time,
                        "end": end_time,
                        "note": note
                    })
            except Exception as e:
                print(f"Warning: Could not parse time range '{time_range}': {e}")
                continue

        return schedule_data

    except Exception as e:
        print(f"Error parsing markdown schedule: {e}")
        traceback.print_exc()
        return None


def parse_pdf_with_claude(pdf_path, pool_name):
    """
    Use Claude to parse the pool schedule PDF and extract family swim times.
    Returns a dict in the format: {weekday: [swim_slots]}
    """
    try:
        with open(pdf_path, 'rb') as f:
            pdf_data = base64.standard_b64encode(f.read()).decode('utf-8')

        client = Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""Please analyze this pool schedule PDF for {pool_name} and extract all Family Swim and Parent Child Swim times.

I need the data in this exact JSON format:
{{
    "Saturday": [
        {{"pool": "{pool_name}", "weekday": "Saturday", "start": "9:00AM", "end": "10:30AM", "note": "Family Swim"}},
        ...
    ],
    "Sunday": [...],
    "Monday": [...],
    "Tuesday": [...],
    "Wednesday": [...],
    "Thursday": [...],
    "Friday": [...]
}}

Important formatting rules:
1. Times must be formatted like "9:00AM" or "2:30PM" (no space between time and AM/PM)
2. Use full weekday names: Saturday, Sunday, Monday, Tuesday, Wednesday, Thursday, Friday
3. For the "note" field, use exactly one of these:
   - "Family Swim" for general family swim times
   - "Parent Child Swim" for parent/child specific times
   - "Family Swim in Small Pool" if it mentions a small pool for families
   - "Parent Child Swim in Small Pool" if it mentions a small pool for parent/child
   - "Parent Child Swim on Steps" if it mentions steps for parent/child
4. If no swims are scheduled for a day, use an empty array []
5. ONLY include drop-in/open swim times for families or parent/child - do NOT include:
   - Lap swim
   - Any swim lessons or classes, including:
     * Learn to Swim
     * Parent Child Intro, Parent Child I, Parent Child II, etc.
     * Youth Swim Lessons
     * Adult Swim Lessons
     * Any other instructional programs
   - Aqua aerobics or water fitness
   - Swim team or competitive swimming
   - Any other structured activities or classes
6. Return ONLY the JSON, no other text

Please extract all family swim and parent child swim times from this schedule."""

        message = client.messages.create(
            model="claude-opus-4-1-20250805",
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

        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()

        schedule_data = json.loads(response_text)
        return schedule_data

    except Exception as e:
        print(f"Error parsing PDF with Claude: {e}")
        traceback.print_exc()
        return None


def get_pool_schedule_from_pdf(pool_name, facility_url, current_date, pools_list, pdf_cache_dir="/tmp"):
    """
    Complete workflow to get pool schedule from PDF.
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

        # Step 4: Extract family swim times using day-by-day approach
        print(f"Extracting family swim times (day-by-day)...")
        family_swim_data = extract_family_swim_day_by_day(pdf_path, pool_name)

        # Fallback to markdown approach if day-by-day fails
        if not family_swim_data:
            print(f"Day-by-day approach failed, trying markdown approach...")
            markdown_table = pdf_table_to_markdown(pdf_path, pool_name)
            if markdown_table:
                print(f"Markdown table preview (first 500 chars):")
                print(markdown_table[:500])
                print("\nParsing markdown table...")
                family_swim_data = parse_markdown_schedule(markdown_table, pool_name)

        # Final fallback to direct extraction
        if not family_swim_data:
            print(f"Markdown approach failed, falling back to direct extraction...")
            family_swim_data = parse_pdf_with_claude(pdf_path, pool_name)

        if not family_swim_data:
            print(f"Failed to extract family swim times for {pool_name}")
            return None

        # Step 5: Extract lap swim times (only for pools with secret swim times)
        SECRET_SWIM_POOLS = ["Balboa Pool", "Hamilton Pool", "Garfield Pool"]

        if pool_name in SECRET_SWIM_POOLS:
            print(f"Extracting lap swim times...")
            lap_swim_data = extract_lap_swim_times(pdf_path, pool_name)
            if not lap_swim_data:
                print(f"Failed to extract lap swim times for {pool_name}")
                return None

            # Step 6: Extract ALL activities (to detect conflicts with classes/lessons)
            print(f"Extracting all activities (to detect class conflicts)...")
            all_activities_data = extract_all_activities(pdf_path, pool_name)
            if not all_activities_data:
                print(f"Warning: Failed to extract all activities for {pool_name}, continuing without class detection")

            # Step 7: Combine and add secret swim times
            print(f"Adding secret swim times...")
            combined_data = add_secret_swim_times(family_swim_data, lap_swim_data, pool_name, all_activities_data)
        else:
            print(f"Skipping lap swim extraction (not needed for {pool_name})")
            combined_data = family_swim_data

        print(f"✓ Successfully processed {pool_name}")
        return combined_data

    except Exception as e:
        print(f"Error processing {pool_name}: {e}")
        traceback.print_exc()
        return None
