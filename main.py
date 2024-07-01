import xvfbwrapper
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.firefox import options, service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from os import environ
from time import sleep
from urllib.parse import urlencode

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

print("ruth debug print")


class SwimSlot:
  # category is morning, afternoon, evening
  def __init__(self, pool, weekday, start, end, category):
    self.pool = pool
    self.weekday = weekday
    self.start = start
    self.end = end
    self.category = category


options = options.Options()
options.binary_location = environ["FIREFOX"]

entries = []

# first, make sure that all family swim is added to the spreadsheet
for pool in pools:
  print("first pool")
  url_params = {
      "activity_select_param": "2",
      "viewMode": "list",
      "center_ids": center_id[pool],
      "activity_keyword": family_swim
  }
  try:
    url = base_url + "?" + urlencode(url_params)
    print(url)

    with xvfbwrapper.Xvfb(), webdriver.Firefox(
        options=options,
        service=service.Service(log_path="../gecko.log")) as driver:
      # with webdriver.Firefox(options=options) as driver:
      actions = ActionChains(driver)
      driver.get(url)
      # assert "Python" in driver.title
      # elem = driver.find_element(By.NAME, "q")
      # elem.clear()
      # elem.send_keys("pycon")
      # elem.send_keys(Keys.RETURN)
      # assert "No results found." not in driver.page_source
      print(driver.title)

    # driver = webdriver.Chrome(options=chrome_options)
    # driver.get(url)
    # soup = BeautifulSoup(driver.page_source, features="html.parser")
    # driver.quit()
    # activities = soup.find_all("div", class_="activity-card")
    # print(activities)
  except Exception as e:
    print(f'An unexpected error occurred: {e}')
  break
# second, add "secret swim": balboa lap swim allows kids on the steps, mlk lap swim allows kids in the tot wading pool, hamilton families can swim in the small pool during lap swim if nothing else is scheduled at that time (check for duplication w existing family swim schedule)

# searching by date/time looks like this
# https://anc.apm.activecommunities.com/sfrecpark/activity/search?time_after_str=12%3A00&days_of_week=0000000&activity_select_param=2&time_before_str=13%3A00&date_before=2024-06-01&date_after=2024-06-01&viewMode=list
# for June 1st, 12pm to 1pm
