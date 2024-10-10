import constants

import datetime
import functools
import json
import os
import requests
import time
import traceback

from bs4 import BeautifulSoup
from felt_python import elements
from urllib import request
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

NORTH_BEACH = "North Beach Pool"
HAMILTON = "Hamilton Pool"
ROSSI = "Rossi Pool"
MISSION = "Mission Community Pool"
GARFIELD = "Garfield Pool"
SAVA = "Sava Pool"
BALBOA = "Balboa Pool"
MLK = "Martin Luther King Jr Pool"
COFFMAN = "Coffman Pool"

POOLS = [
    NORTH_BEACH, HAMILTON, ROSSI, MISSION, GARFIELD, SAVA, BALBOA, MLK, COFFMAN
]

SECRET_LAP_SWIM_POOLS = {
    BALBOA: "Parent Child Swim on Steps",
    HAMILTON: "Family Swim in Small Pool"
}

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

POOL_GROUP = "pool_group"

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
PARENT_CHILD_SWIM = "drop in parent child swim"
LAP_SWIM = "lap swim"

MAP_DATA_DIR = "map_data"


@functools.total_ordering
class SwimSlot:

    def __init__(self, pool, weekday, start, end, note):
        self.pool = pool
        self.weekday = weekday
        self.start = start
        self.end = end
        self.start_12h = self.start.strftime("%I:%M%p").lstrip('0')
        self.end_12h = self.end.strftime("%I:%M%p").lstrip('0')
        self.timeslot_string = f"{self.start_12h} - {self.end_12h}"
        self.note = note

    def __str__(self):
        return f"SwimSlot({self.pool}, {self.weekday}, {self.start}, {self.end})"

    def spreadsheet_output(self):
        # convert times from 18:30:00 to more human readable e.g. 6:30pm
        start_12h = self.start.strftime("%I:%M%p").lstrip('0')
        end_12h = self.end.strftime("%I:%M%p").lstrip('0')
        # convert weekday from short name e.g. "Mon" to long name e.g. "Monday"
        return f"{self.pool},{WEEKDAY_CONVERSION[self.weekday]},{start_12h},{end_12h},{self.note}\n"

    def dict_output(self):
        return_dict = {}
        return_dict["pool"] = self.pool
        # convert weekday from short name e.g. "Mon" to long name e.g. "Monday"
        return_dict["weekday"] = WEEKDAY_CONVERSION[self.weekday]
        # convert times from 18:30:00 to more human readable e.g. 6:30pm
        return_dict["start"] = self.start.strftime("%I:%M%p").lstrip('0')
        return_dict["end"] = self.end.strftime("%I:%M%p").lstrip('0')
        return_dict["note"] = self.note
        return return_dict

    def time_str(self):
        return f"{self.start_12h} - {self.end_12h}"

    def __eq__(self, other):
        return self.start == other.start

    def __lt__(self, other):
        return self.start < other.start


def get_swim_slot_start(swim_slot):
    return swim_slot.start


class OrderedCatalog:
    # organized by pools, weekday, time of day (morning, afternoon, evening)
    def __init__(self):
        self.catalog = {}
        self.create_catalog_structure()

    def create_catalog_structure(self):
        for pool in POOLS:
            self.catalog[pool] = {}
            for weekday in WEEKDAYS:
                self.catalog[pool][weekday] = []

    def add(self, swim_slot):
        self.catalog[swim_slot.pool][swim_slot.weekday].append(swim_slot)

    def sort_all(self):
        for pool in self.catalog:
            for weekday in self.catalog[pool]:
                self.catalog[pool][weekday].sort(key=get_swim_slot_start)

    def output_lines(self):
        lines = []
        for pool in self.catalog:
            for weekday in self.catalog[pool]:
                for slot in self.catalog[pool][weekday]:
                    lines.append(slot.spreadsheet_output())
        return lines

    def get_slot_list(self):
        slot_list = []
        for pool in self.catalog:
            for weekday in self.catalog[pool]:
                slot_list.extend(self.catalog[pool][weekday])
        return slot_list

    def make_deletion_marks(self):
        self.deletion_marks = {}
        for pool in POOLS:
            self.deletion_marks[pool] = {}
            for weekday in WEEKDAYS:
                self.deletion_marks[pool][weekday] = [False] * len(
                    self.catalog[pool][weekday])

    # ASSUMES THAT SLOTS HAVE BEEN SORTED
    def mark_conflicting_lap_swim(self, swim_slot):
        same_day_slots = self.catalog[swim_slot.pool][swim_slot.weekday]
        for i in range(len(same_day_slots)):
            catalog_slot = same_day_slots[i]
            if (swim_slot.start >= catalog_slot.start
                    and swim_slot.start < catalog_slot.start) or (
                        swim_slot.end > catalog_slot.start
                        and swim_slot.end <= catalog_slot.end):
                self.deletion_marks[catalog_slot.pool][
                    catalog_slot.weekday][i] = True

    def delete_conflicting_lap_swim(self):
        try:
            for pool in self.catalog:
                for weekday in self.catalog[pool]:
                    for i in reverse(range(len(self.catalog[pool][weekday]))):
                        if self.deletion_marks[pool][weekday][i]:
                            self.catalog[pool][weekday].pop(i)
        except Exception as e:
            print(e)
            traceback.print_exc()


def string_to_time(time_str):
    time_array = time_str.split(":")
    return datetime.time(int(time_array[0]), int(time_array[1]),
                         int(time_array[2]))


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


def schedule_to_swimslots(schedule, ordered_catalog, note=""):
    for slot in schedule:
        weekdays = slot["weekdays"].split(",")
        start_time = slot["starting_time"]
        end_time = slot["ending_time"]
        for weekday in weekdays:
            clean_weekday = weekday.strip()
            if clean_weekday == "Weekend":
                ordered_catalog.add(
                    SwimSlot(pool, SAT, string_to_time(start_time),
                             string_to_time(end_time), note))
                ordered_catalog.add(
                    SwimSlot(pool, SUN, string_to_time(start_time),
                             string_to_time(end_time), note))
            else:
                ordered_catalog.add(
                    SwimSlot(pool, clean_weekday, string_to_time(start_time),
                             string_to_time(end_time), note))
            ordered_catalog.add(
                SwimSlot(pool, clean_weekday, string_to_time(start_time),
                         string_to_time(end_time), note))


def is_currently_active(data):
    if "current_date" in data["body"]:
        current_date_string = data["body"]["current_date"]
        current_date = datetime.datetime.strptime(current_date_string,
                                                  '%Y-%m-%d %H:%M:%S').date()
    else:
        current_date = datetime.date.today()
    if "beginning_date" in data["body"]["meeting_and_registration_dates"][
            "activity_patterns"][0] and "ending_date" in data["body"][
                "meeting_and_registration_dates"]["activity_patterns"][0]:
        beginning_date_string = data["body"]["meeting_and_registration_dates"][
            "activity_patterns"][0]["beginning_date"]
        ending_date_string = data["body"]["meeting_and_registration_dates"][
            "activity_patterns"][0]["ending_date"]
        beginning_date = datetime.datetime.strptime(beginning_date_string,
                                                    '%Y-%m-%d').date()
        ending_date = datetime.datetime.strptime(ending_date_string,
                                                 '%Y-%m-%d').date()
        if current_date < beginning_date or current_date > ending_date:
            return False
    return True


def process_entries(results, entries, note="", exclude=None):
    lowercase_exclude = None
    if exclude:
        lowercase_exclude = exclude.lower()
    try:
        for item in results:
            if exclude:
                activity_name = item["name"]
                if lowercase_exclude in activity_name.lower():
                    return
            activity_ids = get_subactivities(item)
            for activity_id in activity_ids:
                try:
                    with request.urlopen(
                            f"{ACTIVITY_URL}/{activity_id}") as url:
                        data = json.load(url)
                        # make sure that the listing is CURRENTLY active
                        if not is_currently_active(data):
                            return
                        activity_schedules = get_activity_schedule(data)
                        for activity in activity_schedules:
                            slots = activity["pattern_dates"]
                            schedule_to_swimslots(slots, entries, note=note)
                except HTTPError as e:
                    print(f'HTTP error occurred: {e.code} - {e.reason}')
                except URLError as e:
                    print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        print(traceback.format_exc())


def get_search_results(request_body):
    try:
        response = requests.post(SWIM_API_URL,
                                 headers=HEADERS,
                                 data=json.dumps(request_body))
        current_page = response.json()
        results = current_page["body"]["activity_items"]
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        print(traceback.format_exc())
    return results


ordered_catalog = OrderedCatalog()

# get family swim slots
for pool in POOLS:
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [CENTER_ID[pool]],
            "activity_keyword": FAMILY_SWIM
        },
        "activity_transfer_pattern": {},
    }
    results = get_search_results(request_body)
    process_entries(results, ordered_catalog, note="Family Swim")

for pool in POOLS:
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [CENTER_ID[pool]],
            "activity_keyword": PARENT_CHILD_SWIM
        },
        "activity_transfer_pattern": {},
    }
    results = get_search_results(request_body)
    process_entries(results, ordered_catalog, note="Parent Child Swim")

# second, add "secret swim":
# * balboa allows kids during lap swim if nothing else is scheduled at that time
# * hamilton allows kids during lap swim if nothing else is scheduled at that time

# get all lap swim slots for pools that have a small and big pool
lap_swim_catalog = OrderedCatalog()

for pool in SECRET_LAP_SWIM_POOLS:
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [CENTER_ID[pool]],
            "activity_keyword": LAP_SWIM
        },
        "activity_transfer_pattern": {},
    }
    results = get_search_results(request_body)
    process_entries(results,
                    lap_swim_catalog,
                    note=SECRET_LAP_SWIM_POOLS[pool])

lap_swim_catalog.sort_all()

non_lap_swim_catalog = OrderedCatalog()

# get all non lap swim entries
for pool in SECRET_LAP_SWIM_POOLS:
    request_body = {
        "activity_search_pattern": {
            "activity_select_param": 2,
            "center_ids": [CENTER_ID[pool]],
            "activity_keyword": "*"
        },
        "activity_transfer_pattern": {},
    }
    results = get_search_results(request_body)
    process_entries(results, non_lap_swim_catalog, exclude=LAP_SWIM)

non_lap_swim_slots = non_lap_swim_catalog.get_slot_list()

lap_swim_catalog.make_deletion_marks()

for slot in non_lap_swim_slots:
    lap_swim_catalog.mark_conflicting_lap_swim(slot)

lap_swim_catalog.delete_conflicting_lap_swim

secret_swim_slots = lap_swim_catalog.get_slot_list()
for slot in secret_swim_slots:
    ordered_catalog.add(slot)

# sort the swim slots chronologically before outputting onto map or spreadsheet
ordered_catalog.sort_all()

# write spreadsheet
timestamp = time.time()
with open(f"{MAP_DATA_DIR}/family_swim_data_{timestamp}.csv",
          "w") as timestamp_csv_file:
    with open(f"{MAP_DATA_DIR}/latest_family_swim_data.csv",
              "w") as latest_csv_file:
        # headings for CSV file
        timestamp_csv_file.write(
            f"Pool name, Weekday, Start time, End time, Note\n")
        latest_csv_file.write(
            f"Pool name, Weekday, Start time, End time, Note\n")
        lines = ordered_catalog.output_lines()
        timestamp_csv_file.writelines(lines)
        latest_csv_file.writelines(lines)

# make pool schedule json for map
pool_schedule_data = {}
for pool in POOLS:
    pool_schedule_data[pool] = {}
    for weekday in WEEKDAYS:
        full_weekday = WEEKDAY_CONVERSION[weekday]
        pool_schedule_data[pool][full_weekday] = []
        for slot in ordered_catalog.catalog[pool][weekday]:
            pool_schedule_data[pool][full_weekday].append(slot.dict_output())

timestamp = time.time()
with open(f"{MAP_DATA_DIR}/family_swim_data_{timestamp}.json",
          "w") as timestamp_json_file:
    json.dump(pool_schedule_data, timestamp_json_file, indent=4)

with open(f"{MAP_DATA_DIR}/latest_family_swim_data.json",
          "w") as latest_json_file:
    json.dump(pool_schedule_data, latest_json_file, indent=4)
