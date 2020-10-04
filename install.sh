#!/bin/bash
#

sudo apt-get -yy update
sudo apt-get -yy install python3-requests python3-tz

wget https://raw.githubusercontent.com/rmoesbergen/airsquitter-scraper/master/airsquitter-scraper.py -O /home/pi/airsquitter-scraper.py
wget https://raw.githubusercontent.com/rmoesbergen/airsquitter-scraper/master/airsquitter-scraper.service -O /home/pi/airsquitter-scraper.service

if [[ ! -f airsquitter-settings.json ]]; then
  wget https://raw.githubusercontent.com/rmoesbergen/airsquitter-scraper/master/airsquitter-settings.json -O /home/pi/airsquitter-settings.json
else
  echo "Keeping existing configuration file"
fi
sudo mv /home/pi/airsquitter-scraper.service /etc/systemd/system/airsquitter-scraper.service
sudo chown root:root /etc/systemd/system/airsquitter-scraper.service
sudo systemctl daemon-reload
sudo systemctl enable airsquitter-scraper.service
