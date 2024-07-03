import requests
import json
from pprint import pprint
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

pools = [
    north_beach, hamilton, rossi, mission, garfield, sava, balboa, mlk, coffman
]

# an example search URL looks like this
# https://anc.apm.activecommunities.com/sfrecpark/activity/search?activity_select_param=2&center_ids=85&activity_keyword=family%20swim&viewMode=list
# center_id represents the swimming pool
# activity_keyword is the text in the search query

SWIM_API_URL = "https://anc.apm.activecommunities.com/sfrecpark/rest/activities/list?locale=en-US"
# PAGINATION = {"order_by": "", "page_number": 1, "total_records_per_page": 20}
HEADERS = {
    "Content-Type": "application/json;charset=utf-8",
    "Accept": "*/*",
    "Sec-Fetch-Site": "same-origin",
    "Accept-Language": "en-CA,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Mode": "cors",
    "Host": "anc.apm.activecommunities.com",
    "Origin": "https://anc.apm.activecommunities.com",
    "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Referer":
    "https://anc.apm.activecommunities.com/sfrecpark/activity/search?activity_select_param=2&center_ids=85&activity_keyword=family%20swim&viewMode=list",
    "Content-Length": "581",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "page_info": '{"order_by":"","page_number":1,"total_records_per_page":20}',
    "X-Requested-With": "XMLHttpRequest",
    "X-CSRF-Token": "4481af30-99dc-45da-981a-72b4439dfe89",
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
        pprint(current_page)
    except HTTPError as e:
        print(f'HTTP error occurred: {e.code} - {e.reason}')
    except URLError as e:
        print(f'Failed to reach server: {e.reason}')
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
    break
# second, add "secret swim": balboa lap swim allows kids on the steps, mlk lap swim allows kids in the tot wading pool, hamilton families can swim in the small pool during lap swim if nothing else is scheduled at that time (check for duplication w existing family swim schedule)

# searching by date/time looks like this
# https://anc.apm.activecommunities.com/sfrecpark/activity/search?time_after_str=12%3A00&days_of_week=0000000&activity_select_param=2&time_before_str=13%3A00&date_before=2024-06-01&date_after=2024-06-01&viewMode=list
# for June 1st, 12pm to 1pm
