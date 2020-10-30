#!/usr/bin/env python3
#

import requests
import json
import csv
import pytz
import argparse
from os import path
from datetime import datetime
from time import sleep


class Settings:
    def __init__(self, filename="airsquitter-settings.json"):
        with open(filename, "r") as settings_file:
            self.settings = json.load(settings_file)

    def __getattr__(self, item):
        return self.settings.get(item)


class Flight:
    def __init__(self, flight_data):
        self.data = flight_data
        self.fields = ["uti", "ns", "hex", "fli", "src", "ava", "lat", "lon", "alt", "gda", "spd", "trk", "vrt", "tmp",
                       "wsp", "wdi", "cat", "org", "dst", "opr", "typ", "reg", "dis", "dbm", "cou", "squ", "tru", "lla",
                       "alr", "spi", "pic", "altg"]

    def get(self, item, default):
        return self.__getattr__(item)

    def keys(self):
        return self.fields

    def __getattr__(self, item):
        if item == 'uti':
            timestamp = self.data.get(item)
            if timestamp is not None:
                dt = datetime.fromtimestamp(timestamp, pytz.timezone('Europe/Amsterdam'))
                return dt.strftime('%Y-%m-%d %H:%M:%S')

        if item == 'spd':
            # Speed kts -> km/s
            knots = self.data.get(item)
            if knots is not None:
                knots = round(knots * 1.85200)
            return knots

        if item in ['alt', 'altg', 'alts']:
            # Feet -> Meters
            alt = self.data.get(item)
            if alt is not None:
                alt = round(alt * 0.3048)
            return alt

        return self.data.get(item)

    def __iter__(self):
        for field in self.fields:
            yield field, self.__getattr__(field)

    def _get_altitude(self):
        altitude = self.altg
        if altitude is None or altitude < 0:
            altitude = self.alt
        return altitude

    altitude = property(_get_altitude)


# Remember flight codes for 'duration' seconds
class DeDuplicator:
    def __init__(self, filename, duration):
        self.filename = filename
        self.duration = duration  # In seconds
        if path.exists(self.filename):
            with open(self.filename, "r") as history_file:
                self.seen = json.load(history_file)
        else:
            self.seen = {}

    def remember(self, flight):
        self.seen[flight.hex] = int(datetime.now().timestamp())
        with open(self.filename, "w+") as history_file:
            history_file.write(json.dumps(self.seen))

    def have_seen(self, flight):
        # Expire all records older than self.duration minutes
        to_remove = []
        for entry, dt in self.seen.items():
            if dt < datetime.now().timestamp() - self.duration:
                to_remove.append(entry)
        for entry_to_remove in to_remove:
            del self.seen[entry_to_remove]

        return flight.hex in self.seen


class CsvLogger:
    # Filename can contain datetime format specifiers like %M
    def __init__(self, filename):
        self.filename = filename

    def current_filename(self):
        return datetime.now().strftime(self.filename)

    # Logs a Flight object to CSV
    def log(self, flight):
        filename = self.current_filename()
        write_header = not path.exists(filename)
        with open(filename, "a+") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=flight.fields, quoting=csv.QUOTE_NONNUMERIC, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            writer.writerow(flight)


class FileLogger:
    def __init__(self, filename):
        self.filename = filename

    def log(self, text):
        if self.filename is not None and self.filename != "":
            with open(self.filename, "a+") as logfile:
                logfile.write(text + "\n")


class Scraper:
    def __init__(self, configfile):
        self.settings = Settings(configfile)
        self.log = FileLogger(self.settings.log_file)
        self.csv = CsvLogger(self.settings.csv_file)
        self.dedup = DeDuplicator(self.settings.history_file, self.settings.keep_history)

    def poll_url(self):
        response = requests.get(self.settings.api_url)

        self.log.log(response.content.decode())

        if not response.ok:
            self.log.log(f"Probleem bij het opvragen van API gegevens: {response.content}")
            return

        flights = response.json()
        for flight_data in flights:
            flight = Flight(flight_data)
            # Check lat/lon
            if flight.lat is None or flight.lat > self.settings.lamax or flight.lat < self.settings.lamin:
                self.log.log(f"Skipping {flight.hex}: no latitude match")
                continue
            if flight.lon is None or flight.lon > self.settings.lomax or flight.lon < self.settings.lomin:
                self.log.log(f"Skipping {flight.hex}: no longitude match")
                continue

            # Check and filter altitude
            if flight.altitude is None:
                self.log.log(f"Skipping {flight.hex}: altitude is None")
                continue

            if flight.altitude > self.settings.max_geo_altitude:
                # Flight is above maximum altitude > skip this record
                self.log.log(f"Skipping {flight.hex}: altitude is above maximum {self.settings.max_geo_altitude}")
                continue

            # If flight is on the ground -> skip
            if flight.gda == 'G':
                self.log.log(f"Skipping {flight.hex}: aircraft is on the ground")
                continue

            if flight.fli is None or flight.fli == "":
                # Flight has no callsign yet, skip this record for now
                self.log.log(f"Skipping {flight.hex}: aircraft has no or empty callsign")
                continue

            # Check and filter speed
            if flight.spd < self.settings.min_speed:
                # Flight is in the air, but speed is too low, probably on the ground
                self.log.log(f"Skipping {flight.hex}: aircraft speed is lower than configured minimum")
                continue

            # Flight should be logged, but only not previously logged
            if not self.dedup.have_seen(flight):
                self.csv.log(flight)
                self.dedup.remember(flight)
            else:
                self.log.log(f"Skipping {flight.hex}: aircraft was previously logged")

    def run(self):
        while True:
            self.poll_url()
            sleep(self.settings.poll_interval)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--configfile', help='Path to configuration JSON file', default='airsquitter-settings.json')
    config = parser.parse_args()

    scraper = Scraper(config.configfile)
    scraper.run()
