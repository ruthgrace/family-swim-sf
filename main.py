from bs4 import BeautifulSoup
from urllib.parse import urlencode
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

pools = [
    north_beach, hamilton, rossi, mission, garfield, sava, balboa, mlk, coffman
]

# an example search URL looks like this
# https://anc.apm.activecommunities.com/sfrecpark/activity/search?activity_select_param=2&center_ids=85&activity_keyword=family%20swim&viewMode=list
# center_id represents the swimming pool
# activity_keyword is the text in the search query

base_url = "https://anc.apm.activecommunities.com/sfrecpark/activity/search"

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
  url_params = {
      "activity_select_param": "2",
      "viewMode": "list",
      "center_ids": center_id[pool],
      "activity_keyword": family_swim
  }
  try:
    page = urlopen(base_url + "?" + urlencode(url_params)).read()
    soup = BeautifulSoup(page)
    print(soup)
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
