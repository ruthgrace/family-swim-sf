# family-swim-sf
generate map of when family swim is scheduled at public pools

## set up
This is hosted on Ruth's server. It uses Python 3.12
0. make sure you have Python 3.12 installed. I used [these instructions](https://wiki.crowncloud.net/?How_to_Install_Python_3_12_on_AlmaLinux_9) for getting it on almalinux 9. But I also had to `sudo dnf install bzip2-devel xz-devel libffi-devel` to get it to work.
1. clone this repo to /var/www/
2. `cd family-swim-sf`
3. `python3.12 -m venv venv`
4. `source venv/bin/activate`
5. `pip3.12 install -r requirements.txt`
6. hook up domain (currently swimmap.joyfulparenting.com)
7. set up SSL certs
```
sudo ln -fs /var/www/family-swim-sf/nginx/family-swim-sf.bootstrap /etc/nginx/sites-available/family-swim-sf
sudo ln -fs /etc/nginx/sites-available/family-swim-sf /etc/nginx/sites-enabled/family-swim-sf

sudo service nginx reload

sudo certbot certonly --force-renewal -a webroot -w /var/www/family-swim-sf -d swimmap.joyfulparentingsf.com -w /var/www/family-swim-sf -d swim.joyfulparentingsf.com

sudo ln -fs /var/www/family-swim-sf/nginx/family-swim-sf /etc/nginx/sites-available/family-swim-sf
sudo ln -fs /etc/nginx/sites-available/family-swim-sf /etc/nginx/sites-enabled/family-swim-sf

sudo service nginx reload
```
5. in frontend dir
```
npm install
npm run build
```

# update map data manually

```
python3.12 main.py
```

# 2024-10-29 the below is all outdated now

## set up for updating map

1. make a `constants.py` file to point to the specific map you want to update.
```
MAP_ID = "my_fake_map_id_1234"
PROJECT_ID = "my_fake_project_id_1234"
FELT_TOKEN = "my_fake_felt_api_token_1234"
```

Replace `map_id` and `project_id` values with those from your map. Click the Settings gear to see them. I've redacted mine but here is where you can find yours.

![Screenshot of map settings screen after clicking Settings gear on a felt.com map](https://github.com/ruthgrace/family-swim-sf/assets/6069196/d24f3729-50a0-4f2d-a38b-51b9f1ec4c93)

## update map
0. Ask Emeline or Ruth for edit access to the sfkidsswim workspace on Felt.com
1. Start a new map
2. Upload map_data/public_pools.csv to the map
3. Shift click to select all the pool dots. Click Icon and select the swim icon.
4. 
