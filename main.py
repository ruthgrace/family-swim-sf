import requests
import json
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from urllib import request
from urllib.request import urlopen
from urllib.error import HTTPError
from urllib.error import URLError

north_beach = "North Beach"
hamilton = "Hamilton"
rossi = "Rossi"
mission = "Mission"
garfield = "Garfield"
sava = "Sava"
balboa = "Balboa"
mlk = "Martin Luther King Jr"
coffman = "Coffman"

# swim slot categories
MORNING = "morning"
AFTERNOON = "afternoon"
EVENING = "evening"

pools = [
    north_beach, hamilton, rossi, mission, garfield, sava, balboa, mlk, coffman
]

secret_lap_swim_pools = [balboa, hamilton]

# an example search URL looks like this
# https://anc.apm.activecommunities.com/sfrecpark/activity/search?activity_select_param=2&center_ids=85&activity_keyword=family%20swim&viewMode=list
# center_id represents the swimming pool
# activity_keyword is the text in the search query

SWIM_API_URL = "https://anc.apm.activecommunities.com/sfrecpark/rest/activities/list?locale=en-US"
ACTIVITY_URL = "https://anc.apm.activecommunities.com/sfrecpark/rest/activity/detail/meetingandregistrationdates"
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
    north_beach: "198",
    hamilton: "88",
    rossi: "107",
    mission: "181",
    garfield: "87",
    sava: "108",
    balboa: "85",
    mlk: "177",
    coffman: "86"
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


entries = []

# first, make sure that all family swim is added to the spreadsheet
for pool in pools:
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
                                                 start_time, end_time,
                                                 category))
                                    print(entries[-1])
            except HTTPError as e:
                print(f'HTTP error occurred: {e.code} - {e.reason}')
            except URLError as e:
                print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')

# second, add "secret swim":
# * balboa allows kids during lap swim if nothing else is scheduled at that time
# * hamilton allows kids during lap swim if nothing else is scheduled at that time
# * ask MLK when the tot pool is open - are families always allowed in the tot pool?

lap_swim_entries = {}

for pool in secret_lap_swim_pools:
    lap_swim_entries[pool] = []
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
                            start_time = slot["starting_time"]
                            end_time = slot["ending_time"]
                            for weekday in weekdays:
                                lap_swim_entries[pool].append(
                                    SwimSlot(pool, weekday.strip(), start_time,
                                             end_time, "none"))
                                print(f"LAP SWIM {lap_swim_entries[pool][-1]}")
            except HTTPError as e:
                print(f'HTTP error occurred: {e.code} - {e.reason}')
            except URLError as e:
                print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
