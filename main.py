import datetime
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
MORNING = "morning"
AFTERNOON = "afternoon"
EVENING = "evening"

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

WEEKDAYS = [MON, TUE, WED, THU, FRI, SAT, SUN]

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

center_id = {
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

family_swim = "family swim"
lap_swim = "lap swim"


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


TEST_SLOT_START = datetime.time(6, 30, 0)


def remove_conflicting_lap_swim(slot, lap_swim_slots, overlap):
    for i in range(len(lap_swim_slots[slot.weekday])):
        lap_swim_slot = lap_swim_slots[slot.weekday][i]
        if slot.pool == lap_swim_slot.pool and slot.weekday == lap_swim_slot.weekday:
            if (slot.start >= lap_swim_slot.start and slot.start
                    < lap_swim_slot.end) or (slot.end <= lap_swim_slot.end and
                                             slot.end > lap_swim_slot.start):
                overlap[slot.weekday][i] = True
                return


"""
entries = []

# first, make sure that all family swim is added to the spreadsheet
for pool in POOLS = [:
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [center_id[pool]],
            "activity_keyword": "family swim"
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
                    activity_schedules = data["body"][
                        "meeting_and_registration_dates"]["activity_patterns"]
                    for activity in activity_schedules:
                        slots = activity["pattern_dates"]
                        for slot in slots:
                            weekdays = slot["weekdays"].split(",")
                            start_time = slot["starting_time"]
                            end_time = slot["ending_time"]
                            for weekday in weekdays:
                                categories = get_categories(
                                    start_time, end_time)
                                for category in categories:
                                    entries.append(
                                        SwimSlot(pool, weekday.strip(),
                                                 string_to_time(start_time), string_to_time(end_time),
                                                 category))
                                    print(entries[-1])
            except HTTPError as e:
                print(f'HTTP error occurred: {e.code} - {e.reason}')
            except URLError as e:
                print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        print(traceback.format_exc())
"""
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
            "center_ids": [center_id[pool]],
            "activity_keyword": "lap swim"
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
                    activity_schedules = data["body"][
                        "meeting_and_registration_dates"]["activity_patterns"]
                    for activity in activity_schedules:
                        slots = activity["pattern_dates"]
                        for slot in slots:
                            weekdays = slot["weekdays"].split(",")
                            for weekday in weekdays:
                                clean_weekday = weekday.strip()
                                lap_swim_entries[pool][clean_weekday].append(
                                    SwimSlot(
                                        pool, clean_weekday,
                                        string_to_time(slot["starting_time"]),
                                        string_to_time(slot["ending_time"]),
                                        "none"))
            except HTTPError as e:
                print(f'HTTP error occurred: {e.code} - {e.reason}')
            except URLError as e:
                print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        print(traceback.format_exc())

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
            "center_ids": [center_id[pool]],
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
            activity_ids = [item["id"]]
            activity_name = item["name"]
            if "lap swim" not in activity_name.lower():
                # sometimes a listing that does not have meeting times has sub listings that do have meeting times
                if "num_of_sub_activities" in item and item[
                        "num_of_sub_activities"] > 0:
                    if "sub_activities" in item and len(
                            item["sub_activity_ids"]) > 0:
                        activity_ids = item["sub_activity_ids"]
                    else:
                        try:
                            request_body = {"locale": "en-US"}
                            response = requests.post(
                                f"{SUBACTIVITY_URL}/{activity_ids[0]}",
                                headers=HEADERS,
                                data=json.dumps(request_body))
                            current_page = response.json()
                            sub_activities = current_page["body"][
                                "sub_activities"]
                            for sub_activity_data in sub_activities:
                                activity_ids.append(sub_activity_data["id"])
                        except HTTPError as e:
                            print(
                                f'HTTP error occurred: {e.code} - {e.reason}')
                        except URLError as e:
                            print(f'Failed to reach server: {e.reason}')
                for activity_id in activity_ids:
                    try:
                        with request.urlopen(
                                f"{ACTIVITY_URL}/{activity_id}") as url:
                            data = json.load(url)
                            if "meeting_and_registration_dates" in data[
                                    "body"]:
                                if "no_meeting_dates" not in data["body"][
                                        "meeting_and_registration_dates"] or not data[
                                            "body"][
                                                "meeting_and_registration_dates"][
                                                    "no_meeting_dates"]:
                                    if "activity_patterns" in data["body"][
                                            "meeting_and_registration_dates"]:
                                        activity_schedules = data["body"][
                                            "meeting_and_registration_dates"][
                                                "activity_patterns"]
                                        for activity in activity_schedules:
                                            slots = activity["pattern_dates"]
                                            for slot in slots:
                                                weekdays = slot[
                                                    "weekdays"].split(",")
                                                for weekday in weekdays:
                                                    remove_conflicting_lap_swim(
                                                        SwimSlot(
                                                            pool,
                                                            weekday.strip(),
                                                            string_to_time(slot[
                                                                "starting_time"]
                                                                           ),
                                                            string_to_time(slot[
                                                                "ending_time"]
                                                                           ),
                                                            "none"),
                                                        lap_swim_entries[pool],
                                                        overlap)
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
                print(f"SECRET SWIM: {lap_swim_entries[pool][weekday][i]}")
