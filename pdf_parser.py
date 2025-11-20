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
    """Filter documents for schedule PDFs and select the most appropriate one"""
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

    # Fallback: if no pool-specific PDF found, look for generic "schedule" PDFs
    if not schedule_docs:
        for doc in documents:
            doc_name_lower = doc['name'].lower()
            if 'schedule' in doc_name_lower:
                # Make sure it's not specifically for a different pool
                other_pools = [p.lower().replace(' pool', '') for p in pools_list if p.lower() != pool_name_lower]
                # Exclude specific pool names but allow generic ones like "Mission Pool Schedule"
                is_other_specific_pool = any(
                    other_pool in doc_name_lower and other_pool not in ['mission']
                    for other_pool in other_pools
                )

                if not is_other_specific_pool:
                    schedule_docs.append(doc)

    if not schedule_docs:
        return None

    if len(schedule_docs) == 1:
        return schedule_docs[0]

    # Select based on current season
    current_year = current_date.year
    current_month = current_date.month

    if current_month in [12, 1, 2]:
        current_season = 'winter'
    elif current_month in [3, 4, 5]:
        current_season = 'spring'
    elif current_month in [6, 7, 8]:
        current_season = 'summer'
    else:
        current_season = 'fall'

    best_doc = None
    best_score = -1

    for doc in schedule_docs:
        doc_name_lower = doc['name'].lower()
        score = 0

        if str(current_year) in doc_name_lower:
            score += 10
        if current_season in doc_name_lower:
            score += 5
        if pool_name_lower.replace(' pool', '') in doc_name_lower:
            score += 3

        if score > best_score:
            best_score = score
            best_doc = doc

    return best_doc if best_score > 0 else schedule_docs[0]


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


def add_secret_swim_times(family_swim_data, lap_swim_data, pool_name):
    """
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
        family_slots = family_swim_data.get(day, [])

        for lap_slot in lap_slots:
            lap_start = time_to_minutes(lap_slot['start'])
            lap_end = time_to_minutes(lap_slot['end'])

            conflicts = []
            for family_slot in family_slots:
                family_start = time_to_minutes(family_slot['start'])
                family_end = time_to_minutes(family_slot['end'])

                if not (lap_end <= family_start or lap_start >= family_end):
                    conflicts.append((family_start, family_end))

            if not conflicts:
                combined_data[day].append({
                    "pool": pool_name,
                    "weekday": day,
                    "start": lap_slot['start'],
                    "end": lap_slot['end'],
                    "note": secret_swim_note
                })
            else:
                conflicts.sort()
                available_ranges = []
                current_start = lap_start

                for conflict_start, conflict_end in conflicts:
                    if current_start < conflict_start:
                        available_ranges.append((current_start, conflict_start))
                    current_start = max(current_start, conflict_end)

                if current_start < lap_end:
                    available_ranges.append((current_start, lap_end))

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

IMPORTANT: Only include times that are specifically labeled as "Lap Swim". Be very careful to:
- Look at the correct day column
- Do NOT mix up days (e.g., don't put Thursday times into Friday)
- Do NOT include any other activities like classes, lessons, or other swim programs

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
5. ONLY include times specifically labeled as "Lap Swim" - do NOT include:
   - Family swim
   - Learn to Swim or any swim lessons/classes
   - Any other activities
6. Double-check that you have the correct day for each time slot
7. Return ONLY the JSON, no other text

Please carefully extract all lap swim times from this schedule."""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
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

        lap_swim_data = json.loads(response_text)
        return lap_swim_data

    except Exception as e:
        print(f"Error extracting lap swim times with Claude: {e}")
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
            model="claude-sonnet-4-20250514",
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

        # Step 4: Extract family swim times
        print(f"Extracting family swim times...")
        family_swim_data = parse_pdf_with_claude(pdf_path, pool_name)
        if not family_swim_data:
            print(f"Failed to extract family swim times for {pool_name}")
            return None

        # Step 5: Extract lap swim times
        print(f"Extracting lap swim times...")
        lap_swim_data = extract_lap_swim_times(pdf_path, pool_name)
        if not lap_swim_data:
            print(f"Failed to extract lap swim times for {pool_name}")
            return None

        # Step 6: Combine and add secret swim times
        print(f"Adding secret swim times...")
        combined_data = add_secret_swim_times(family_swim_data, lap_swim_data, pool_name)

        print(f"✓ Successfully processed {pool_name}")
        return combined_data

    except Exception as e:
        print(f"Error processing {pool_name}: {e}")
        traceback.print_exc()
        return None
