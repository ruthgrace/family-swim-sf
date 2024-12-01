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

**instructions for UBUNTU**

```
sudo ln -fs /var/www/family-swim-sf/nginx/family-swim-sf.bootstrap /etc/nginx/sites-available/family-swim-sf
sudo ln -fs /etc/nginx/sites-available/family-swim-sf /etc/nginx/sites-enabled/family-swim-sf

sudo service nginx reload

sudo certbot certonly --force-renewal -a webroot -w /var/www/family-swim-sf -d swimmap.joyfulparentingsf.com -w /var/www/family-swim-sf -d swim.joyfulparentingsf.com

sudo ln -fs /var/www/family-swim-sf/nginx/family-swim-sf /etc/nginx/sites-available/family-swim-sf
sudo ln -fs /etc/nginx/sites-available/family-swim-sf /etc/nginx/sites-enabled/family-swim-sf

sudo service nginx reload
```

**instructions for ALMALINUX**

```
sudo ln -fs /var/www/family-swim-sf/nginx/family-swim-sf.bootstrap /etc/nginx/conf.d/family-swim-sf.conf
# ensure nginx config context is httpd_config_t
sudo chcon -t httpd_config_t /etc/nginx/conf.d/family-swim-sf.conf
sudo semanage fcontext -a -t httpd_config_t "/etc/nginx/conf.d(/.*)?"
sudo restorecon -Rv /etc/nginx/conf.d

sudo service nginx reload

# ensure webroot context is httpd_sys_content_t
sudo semanage fcontext -a -t httpd_sys_content_t "/var/www/family-swim-sf(/.*)?"
sudo restorecon -Rv /var/www/family-swim-sf
sudo certbot certonly --force-renewal -a webroot -w /var/www/family-swim-sf -d swimmap.joyfulparentingsf.com -w /var/www/family-swim-sf -d swim.joyfulparentingsf.com

sudo ln -fs /var/www/family-swim-sf/nginx/family-swim-sf /etc/nginx/conf.d/family-swim-sf.conf

sudo service nginx reload
```

5. in frontend dir (`cd frontend`)
```
npm install
npm run build
```

6. set up auto updating cron job (run this as the ruth user so that it can automatically git commit changes)

```
sudo -u ruth crontab -e
```

add this line

```
15 0 * * * venv/bin/python3.12 main.py
```

# update map data manually

```
venv/bin/python3.12 main.py
```

# find logs for debugging

i believe logs from cron will go to `/var/log/cron`. i think these are log rotated so you may see `/var/log/cron-20241201` for example.
