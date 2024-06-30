from bs4 import BeautifulSoup

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

# searching by date/time looks like this
# https://anc.apm.activecommunities.com/sfrecpark/activity/search?time_after_str=12%3A00&days_of_week=0000000&activity_select_param=2&time_before_str=13%3A00&date_before=2024-06-01&date_after=2024-06-01&viewMode=list
# for June 1st, 12pm to 1pm

# soup = BeautifulSoup(html_doc, 'html.parser')
