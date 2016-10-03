#!/usr/bin/python
#
# Based on: https://github.com/pliablepixels/zmhacks/blob/master/arc_zm_iphone.py
import configargparse
import time
import requests
import sys

from math import radians, sin, cos, atan2, sqrt
from pyicloud import PyiCloudService

#Set up logging
import logging
logging.basicConfig(format='%(asctime)s [%(module)8s] [%(levelname)7s] %(message)s', level=logging.INFO)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("connectionpool").setLevel(logging.WARNING)
log = logging.getLogger()

# Global variables
api = None
old_loc = None

# =========================================

def parse_config():
    parser = configargparse.ArgParser(default_config_files=['config.ini'])
    parser.add_argument('-u', '--user', help='Your iCloud username')
    parser.add_argument('-p', '--password', help='Your iCloud password')
    parser.add_argument('-d', '--device', help='The name of the device to query')
    parser.add_argument('-P', '--pause', type=int,
                        help='Number of minutes to pause between location requests', default=5)
    parser.add_argument('-a', '--alarm-url', help='Optional PokeAlarm webhook URL, usually http://localhost:4000')
    parser.add_argument('-m', '--map-url', help='Optional PokemonGo-Map URL, usually http://localhost:5000')
    return parser.parse_args()

def get_icloud_devices():
    global api

    while True:
        try:
            if api is None:
                api = PyiCloudService(cfg.user, cfg.password)
            devices = api.devices
            return devices
        except requests.exceptions.ConnectionError as e:
            log.warning("Error getting iCloud devices (retrying in 10 sec): %s" % e)
            time.sleep(10)
            api = None

# Returns an integer representing the distance between A and B
def get_dist(ptA, ptB):
    latA = radians(ptA[0])
    lngA = radians(ptA[1])
    latB = radians(ptB[0])
    lngB = radians(ptB[1])
    dLat = latB - latA
    dLng = lngB - lngA

    a = sin(dLat / 2) ** 2 + cos(latA) * cos(latB) * sin(dLng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    radius = 6373000  # radius of earth in meters
    dist = c * radius
    return dist

def location_differs(new_loc):
    global old_loc
    if old_loc is None:
        return True
    else:
        return get_dist(old_loc, new_loc) > 50

# ==============================================

cfg = parse_config()
if cfg.alarm_url is None and cfg.map_url is None:
    log.error("Neither alarm-url nor map-url was configured.")
    sys.exit(1)

log.info("starting up for iCloud user %s, device %s, PokeAlarm URL %s, PoGoMap URL %s, %u minutes pause" % (cfg.user, cfg.device, cfg.alarm_url, cfg.map_url, cfg.pause));
alarm_url = None if cfg.alarm_url is None else ("%s/location/" % cfg.alarm_url)
map_url = None if cfg.map_url is None else ("%s/next_loc" % cfg.map_url)

while True:
    for rdev in get_icloud_devices():
        dev = str(rdev)
        if cfg.device in dev:
            log.debug("querying %s" % dev);

            device_loc = rdev.location()
            iter = 1
            while (device_loc is None or device_loc['locationFinished'] != True) and iter < 6:
                log.debug("iterating location, as it is not fresh. sleeping for additional 10 secs")
                time.sleep(10)
                device_loc = rdev.location()
                iter += 1

            if device_loc is None:
                log.info("could not determine location of %s after %u iterations" \
                    % (dev, iter))
            else:
                new_loc = float(device_loc['latitude']), float(device_loc['longitude'])

                if location_differs(new_loc):
                    old_loc = new_loc
                    lat = device_loc['latitude']
                    lon = device_loc['longitude']
                    log.info("got new location (%s,%s after %u iterations) for %s" % (
                        lat, lon, iter, dev))

                    # update PokeAlarm
                    if alarm_url is not None:
                        try:
                            r = requests.post(alarm_url, params = {'location': '%s,%s' % (lat, lon)})
                            hook_result = str(r)
                        except requests.exceptions.ReadTimeout:
                            hook_result = 'read timeout'
                        except requests.exceptions.RequestException as e:
                            hook_result = 'exception: %s' % str(e)
                        log.info("update PokeAlarm result: %s" % hook_result)

                    # update PokemonGo-Map
                    if map_url is not None:
                        try:
                            r = requests.post(map_url, params={'lat': lat, 'lon': lon})
                            hook_result = str(r)
                        except requests.exceptions.ReadTimeout:
                            hook_result = 'read timeout'
                        except requests.exceptions.RequestException as e:
                            hook_result = 'exception: %s' % str(e)
                        log.info("update PokemonGo-Map result: %s" % hook_result)
                else:
                    log.info('location did not change significantly. not updating.')
        else:
            log.debug("Skipping %s" % dev)

    log.info("sleeping %u minutes" % cfg.pause)
    time.sleep(cfg.pause * 60)
