# family-swim-sf
generate map of when family swim is scheduled at public pools

## set up
This is hosted on replit at https://replit.com/@Ruth-GraceGrace/family-swim-sf

It uses Python 3.12

but if you need to run it elsewhere,
```
pip install -r requirements.txt
```

## set up for updating map

1. make a `constants.py` file to point to the specific map you want to update.
```
map_id = my_fake_map_id_1234
project_id = my_fake_project_id_1234
```

Replace `map_id` and `project_id` values with those from your map. Click the Settings gear to see them. I've redacted mine but here is where you can find yours.

![Screenshot of map settings screen after clicking Settings gear on a felt.com map](https://github.com/ruthgrace/family-swim-sf/assets/6069196/d24f3729-50a0-4f2d-a38b-51b9f1ec4c93)

## update map
0. Ask Emeline or Ruth for edit access to the sfkidsswim workspace on Felt.com
1. Start a new map
2. Upload map_data/public_pools.csv to the map
3. Shift click to select all the pool dots. Click Icon and select the swim icon.
4. 
