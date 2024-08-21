import datetime
import time
import requests
import traceback
import json
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from urllib import request
from urllib.request import urlopen
from urllib.error import HTTPError
from urllib.error import URLError

NORTH_BEACH = "North Beach"
HAMILTON = "Hamilton"
ROSSI = "Rossi"
MISSION = "Mission"
GARFIELD = "Garfield"
SAVA = "Sava"
BALBOA = "Balboa"
MLK = "Martin Luther King Jr"
COFFMAN = "Coffman"

# swim slot categories
MORNING = "Morning Family Swim"
AFTERNOON = "Afternoon Family Swim"
EVENING = "Evening Family Swim"

POOLS = [
    NORTH_BEACH, HAMILTON, ROSSI, MISSION, GARFIELD, SAVA, BALBOA, MLK, COFFMAN
]

SECRET_LAP_SWIM_POOLS = [BALBOA, HAMILTON]

MON = "Mon"
TUE = "Tue"
WED = "Wed"
THU = "Thu"
FRI = "Fri"
SAT = "Sat"
SUN = "Sun"

MONDAY = "Monday"
TUESDAY = "Tuesday"
WEDNESDAY = "Wednesday"
THURSDAY = "Thursday"
FRIDAY = "Friday"
SATURDAY = "Saturday"
SUNDAY = "Sunday"

WEEKDAYS = [MON, TUE, WED, THU, FRI, SAT, SUN]

WEEKDAY_CONVERSION = {
    MON: MONDAY,
    TUE: TUESDAY,
    WED: WEDNESDAY,
    THU: THURSDAY,
    FRI: FRIDAY,
    SAT: SATURDAY,
    SUN: SUNDAY
}

# an example search URL looks like this
# https://anc.apm.activecommunities.com/sfrecpark/activity/search?activity_select_param=2&center_ids=85&activity_keyword=family%20swim&viewMode=list
# center_id represents the swimming pool
# activity_keyword is the text in the search query

SWIM_API_URL = "https://anc.apm.activecommunities.com/sfrecpark/rest/activities/list?locale=en-US"
ACTIVITY_URL = "https://anc.apm.activecommunities.com/sfrecpark/rest/activity/detail/meetingandregistrationdates"
SUBACTIVITY_URL = "https://anc.apm.activecommunities.com/sfrecpark/rest/activities/subs"
HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "page_info": '{"order_by":"","page_number":1,"total_records_per_page":30}',
}

# example full request body
# request_body = {
#     "activity_search_pattern": {
#         "skills": [],
#         "time_after_str": "",
#         "days_of_week": None,
#         "activity_select_param": 2,
#         "center_ids": [center_id[pool]],
#         "time_before_str": "",
#         "open_spots": None,
#         "activity_id": None,
#         "activity_category_ids": [],
#         "date_before": "",
#         "min_age": None,
#         "date_after": "",
#         "activity_type_ids": [],
#         "site_ids": [],
#         "for_map": False,
#         "geographic_area_ids": [],
#         "season_ids": [],
#         "activity_department_ids": [],
#         "activity_other_category_ids": [],
#         "child_season_ids": [],
#         "activity_keyword": "family swim",
#         "instructor_ids": [],
#         "max_age": None,
#         "custom_price_from": "",
#         "custom_price_to": "",
#     },
#     "activity_transfer_pattern": {},
# }

CENTER_ID = {
    NORTH_BEACH: "198",
    HAMILTON: "88",
    ROSSI: "107",
    MISSION: "181",
    GARFIELD: "87",
    SAVA: "108",
    BALBOA: "85",
    MLK: "177",
    COFFMAN: "86"
}

FAMILY_SWIM = "family swim"
LAP_SWIM = "lap swim"

MAP_DATA_DIR = "map_data"


class SwimSlot:
    # category is morning, afternoon, evening
    def __init__(self, pool, weekday, start, end, category):
        self.pool = pool
        self.weekday = weekday
        self.start = start
        self.end = end
        self.category = category

    def __str__(self):
        return f"SwimSlot({self.pool}, {self.weekday}, {self.start}, {self.end}, {self.category})"

    def spreadsheet_output(self, note=""):
        # convert times from 18:30:00 to ore human readable e.g. 6:30pm
        start_12h = self.start.strftime("%I:%M%p").lstrip('0')
        end_12h = self.end.strftime("%I:%M%p").lstrip('0')
        # convert weekday from short name e.g. "Mon" to long name e.g. "Monday"
        return f"{self.pool},{WEEKDAY_CONVERSION[self.weekday]},{self.category},{start_12h},{end_12h},{note}\n"


def get_categories(start_time, end_time):
    categories = []
    start_hour = int(start_time.split(":")[0].strip())
    end_hour = int(end_time.split(":")[0].strip())
    if start_hour < 12:
        categories.append(MORNING)
    if end_hour > 12 and start_hour < 17:
        categories.append(AFTERNOON)
    if end_hour > 17:
        categories.append(EVENING)
    return categories


def string_to_time(time_str):
    time_array = time_str.split(":")
    return datetime.time(int(time_array[0]), int(time_array[1]),
                         int(time_array[2]))


def remove_conflicting_lap_swim(slot, lap_swim_slots, overlap):
    for i in range(len(lap_swim_slots[slot.weekday])):
        lap_swim_slot = lap_swim_slots[slot.weekday][i]
        if slot.pool == lap_swim_slot.pool and slot.weekday == lap_swim_slot.weekday:
            if (slot.start >= lap_swim_slot.start and slot.start
                    < lap_swim_slot.end) or (slot.end <= lap_swim_slot.end and
                                             slot.end > lap_swim_slot.start):
                overlap[slot.weekday][i] = True
                return


def add_weekday_arrays(entries):
    for weekday in WEEKDAYS:
        entries[weekday] = []
    return entries


def get_activity_schedule(data):
    return data["body"]["meeting_and_registration_dates"]["activity_patterns"]


def get_subactivities(activity):
    activity_ids = [activity["id"]]
    if "num_of_sub_activities" in activity and activity[
            "num_of_sub_activities"] > 0:
        if "sub_activity_ids" in activity and activity[
                "sub_activity_ids"] and len(activity["sub_activity_ids"]) > 0:
            activity_ids = activity["sub_activity_ids"]
        else:
            try:
                request_body = {"locale": "en-US"}
                response = requests.post(
                    f"{SUBACTIVITY_URL}/{activity_ids[0]}",
                    headers=HEADERS,
                    data=json.dumps(request_body))
                current_page = response.json()
                sub_activities = current_page["body"]["sub_activities"]
                for sub_activity_data in sub_activities:
                    activity_ids.append(sub_activity_data["id"])
            except HTTPError as e:
                print(f'HTTP error occurred: {e.code} - {e.reason}')
            except URLError as e:
                print(f'Failed to reach server: {e.reason}')
    return activity_ids


def schedule_to_swimslots(schedule, swimslots, category=True):
    for slot in schedule:
        weekdays = slot["weekdays"].split(",")
        start_time = slot["starting_time"]
        end_time = slot["ending_time"]
        for weekday in weekdays:
            clean_weekday = weekday.strip()
            if category:
                categories = get_categories(start_time, end_time)
                for category in categories:
                    swimslots[clean_weekday].append(
                        SwimSlot(pool, clean_weekday,
                                 string_to_time(start_time),
                                 string_to_time(end_time), category))
            else:
                swimslots[clean_weekday].append(
                    SwimSlot(pool, clean_weekday, string_to_time(start_time),
                             string_to_time(end_time), "none"))


def get_swim_slots(activity_data):
    if "meeting_and_registration_dates" not in activity_data["body"]:
        return []
    if "no_meeting_dates" in activity_data["body"][
            "meeting_and_registration_dates"] and activity_data["body"][
                "meeting_and_registration_dates"]["no_meeting_dates"]:
        return []
    if "activity_patterns" not in activity_data["body"][
            "meeting_and_registration_dates"]:
        return []
    return activity_data["body"]["meeting_and_registration_dates"][
        "activity_patterns"]


def export_map_data(csv_file, entries, note):
    lines = []
    for weekday in WEEKDAYS:
        for item in entries[weekday]:
            lines.append(item.spreadsheet_output(note))
    csv_file.writelines(lines)

def is_currently_active(data):
    if "current_date" in data["body"]:
        current_date_string = data["body"]["current_date"]
        current_date = datetime.datetime.strptime(current_date_string, '%Y-%m-%d %H:%M:%S').date()
    else:
        current_date = datetime.date.today()
    if "beginning_date" in data["body"]["meeting_and_registration_dates"]["activity_patterns"][0] and "ending_date" in data["body"]["meeting_and_registration_dates"]["activity_patterns"][0]:
        beginning_date_string = data["body"]["meeting_and_registration_dates"]["activity_patterns"][0]["beginning_date"]
        ending_date_string = data["body"]["meeting_and_registration_dates"]["activity_patterns"][0]["ending_date"]
        beginning_date = datetime.datetime.strptime(beginning_date_string, '%Y-%m-%d').date()
        ending_date = datetime.datetime.strptime(ending_date_string, '%Y-%m-%d').date()
        if current_date < beginning_date or current_date > ending_date:
            return False
    return True

entries = {}
entries = add_weekday_arrays(entries)
# first, make sure that all family swim is added to the spreadsheet
for pool in POOLS:
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [CENTER_ID[pool]],
            "activity_keyword": FAMILY_SWIM
        },
        "activity_transfer_pattern": {},
    }
    try:
        response = requests.post(SWIM_API_URL,
                                 headers=HEADERS,
                                 data=json.dumps(request_body))
        current_page = response.json()
        results = current_page["body"]["activity_items"]
        for item in results:
            activity_id = item["id"]
            try:
                with request.urlopen(f"{ACTIVITY_URL}/{activity_id}") as url:
                    data = json.load(url)
                    # make sure that the listing is CURRENTLY active
                    if not is_currently_active(data):
                        continue
                    activity_schedules = get_activity_schedule(data)
                    for activity in activity_schedules:
                        slots = activity["pattern_dates"]
                        schedule_to_swimslots(slots, entries)
            except HTTPError as e:
                print(f'HTTP error occurred: {e.code} - {e.reason}')
            except URLError as e:
                print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        print(traceback.format_exc())

# second, add "secret swim":
# * balboa allows kids during lap swim if nothing else is scheduled at that time
# * hamilton allows kids during lap swim if nothing else is scheduled at that time
# * ask MLK when the tot pool is open - are families always allowed in the tot pool?

# get all lap swim slots for pools that have a small and big pool
lap_swim_entries = {}

for pool in SECRET_LAP_SWIM_POOLS:
    lap_swim_entries[pool] = {}
    for weekday in WEEKDAYS:
        lap_swim_entries[pool][weekday] = []
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [CENTER_ID[pool]],
            "activity_keyword": LAP_SWIM
        },
        "activity_transfer_pattern": {},
    }
    try:
        response = requests.post(SWIM_API_URL,
                                 headers=HEADERS,
                                 data=json.dumps(request_body))
        current_page = response.json()
        results = current_page["body"]["activity_items"]
        for item in results:
            activity_id = item["id"]
            try:
                with request.urlopen(f"{ACTIVITY_URL}/{activity_id}") as url:
                    data = json.load(url)
                    if not is_currently_active(data):
                        continue
                    activity_schedules = get_activity_schedule(data)
                    for activity in activity_schedules:
                        slots = activity["pattern_dates"]
                        schedule_to_swimslots(slots, lap_swim_entries[pool])
            except HTTPError as e:
                print(f'HTTP error occurred: {e.code} - {e.reason}')
            except URLError as e:
                print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        print(traceback.format_exc())

secret_swim_entries = {}
add_weekday_arrays(secret_swim_entries)

# get all non lap swim entries
for pool in lap_swim_entries.keys():
    # this array records true at an index where a scheduled lap swim has an overlapping activity
    overlap = {}
    for weekday in WEEKDAYS:
        overlap[weekday] = [
            False for i in range(len(lap_swim_entries[pool][weekday]))
        ]
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [CENTER_ID[pool]],
            "activity_keyword": "*"
        },
        "activity_transfer_pattern": {},
    }
    try:
        response = requests.post(SWIM_API_URL,
                                 headers=HEADERS,
                                 data=json.dumps(request_body))
        current_page = response.json()
        results = current_page["body"]["activity_items"]
        for item in results:
            activity_name = item["name"]
            if LAP_SWIM not in activity_name.lower():
                # sometimes a listing that does not have meeting times has sub listings that do have meeting times
                activity_ids = get_subactivities(item)
                for activity_id in activity_ids:
                    try:
                        with request.urlopen(
                                f"{ACTIVITY_URL}/{activity_id}") as url:
                            data = json.load(url)
                            if not is_currently_active(data):
                                continue
                            activity_schedules = get_swim_slots(data)
                            for activity in activity_schedules:
                                slots = activity["pattern_dates"]
                                for slot in slots:
                                    weekdays = slot["weekdays"].split(",")
                                    for weekday in weekdays:
                                        if weekday == "Weekend":
                                            remove_conflicting_lap_swim(
                                                SwimSlot(
                                                    pool, "Sat",
                                                    string_to_time(
                                                        slot["starting_time"]),
                                                    string_to_time(
                                                        slot["ending_time"]),
                                                    "none"),
                                                lap_swim_entries[pool], overlap)
                                            remove_conflicting_lap_swim(
                                                SwimSlot(
                                                    pool, "Sun",
                                                    string_to_time(
                                                        slot["starting_time"]),
                                                    string_to_time(
                                                        slot["ending_time"]),
                                                    "none"),
                                                lap_swim_entries[pool], overlap)
                                        else:
                                            remove_conflicting_lap_swim(
                                                SwimSlot(
                                                    pool, weekday.strip(),
                                                    string_to_time(
                                                        slot["starting_time"]),
                                                    string_to_time(
                                                        slot["ending_time"]),
                                                    "none"),
                                                lap_swim_entries[pool], overlap)
                    except HTTPError as e:
                        print(f'HTTP error occurred: {e.code} - {e.reason}')
                    except URLError as e:
                        print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        print(traceback.format_exc())
    for weekday in lap_swim_entries[pool].keys():
        for i in range(len(lap_swim_entries[pool][weekday])):
            if not overlap[weekday][i]:
                secret_swim_entries[weekday].append(
                    lap_swim_entries[pool][weekday][i])

# write spreadsheet
timestamp = time.time()
with open(f"{MAP_DATA_DIR}/family_swim_data_{timestamp}.csv", "a") as csv_file:
    # headings for CSV file
    csv_file.write(
        f"Pool name, Weekday, Time period, Start time, End time, Note\n")
    export_map_data(csv_file, entries, "")
    export_map_data(
        csv_file, secret_swim_entries,
        "secret family swim in small pool or steps during lap swim")
