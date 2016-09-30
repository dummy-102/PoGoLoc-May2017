#!/usr/bin/python
#
# Based on: https://github.com/pliablepixels/zmhacks/blob/master/arc_zm_iphone.py
import configargparse
import time
import requests

from pyicloud import PyiCloudService

#Set up logging
import logging
logging.basicConfig(format='%(asctime)s [%(module)8s] [%(levelname)7s] %(message)s', level=logging.INFO)
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("connectionpool").setLevel(logging.WARNING)
log = logging.getLogger()


def parse_config():
    parser = configargparse.ArgParser(default_config_files=['config.ini'])
    parser.add_argument('-u', '--user', help='Your iCloud username')
    parser.add_argument('-p', '--password', help='Your iCloud password')
    parser.add_argument('-d', '--device', help='The name of the device to query')
    parser.add_argument('-wh', '--webhook', help='PokeAlarm webhook address', default='http://127.0.0.1:4000')
    parser.add_argument('-P', '--pause', type=int,
                        help='Number of minutes to pause between location requests', default=5)
    return parser.parse_args()

cfg = parse_config()
log.info("starting up for iCloud user %s, device %s, webhook %s, %u minutes pause between requests" % (cfg.user, cfg.device, cfg.webhook, cfg.pause));
webhook_url = "%s/location/" % cfg.webhook

# if api.requires_2fa:
#     log.warning("Two step authentication problem")
#     if (not os.isatty(sys.stdin.fileno())):  # cron
#         os.system('cat ' + 'update.log | mail -s "2 factor auth needed" ' + my_email);
#         sys.exit(1)
#     else:
#         print "Two-factor authentication required. Your trusted devices are:"
#         devices = api.trusted_devices
#         for i, device in enumerate(devices):
#             print "  %s: %s" % (i, device.get('deviceName',
#                                               "SMS to %s" % device.get('phoneNumber')))
#         device = click.prompt('Which device would you like to use?', default=0)
#         device = devices[device]
#         if not api.send_verification_code(device):
#             print "Failed to send verification code"
#             sys.exit(1)
#         code = click.prompt('Please enter validation code')
#         if not api.validate_verification_code(device, code):
#             print "Failed to verify verification code"
#             sys.exit(1)

old_loc_str = ""
cur_time = 0

while True:
    new_time = int(time.time())
    if new_time - cur_time > 1200:
        if cur_time > 0:
            log.info("reconnecting to iCloud after 20 minutes...")
        api = PyiCloudService(cfg.user, cfg.password)
        cur_time = new_time

    for rdev in api.devices:
        dev = str(rdev)
        if cfg.device in dev:
            log.debug("querying %s" % dev);

            curr_loc = rdev.location()
            iter = 1
            while (curr_loc is None or curr_loc['locationFinished'] != True) and iter < 6:
                log.debug("iterating location, as it is not fresh. sleeping for additional 10 secs")
                time.sleep(10)
                curr_loc = rdev.location()
                iter += 1

            if curr_loc is None:
                log.info("could not determine location of %s after %u iterations" \
                    % (dev, iter))
            else:
                lat = "%.6f" % float(curr_loc['latitude'])
                lng = "%.6f" % float(curr_loc['longitude'])
                loc_str = '%s,%s' % (lat, lng)

                if loc_str != old_loc_str:
                    try:
                        r = requests.post(webhook_url, params = {'location': loc_str})
                        hook_result = str(r)
                        old_loc_str = loc_str
                    except requests.exceptions.ReadTimeout:
                        hook_result = 'read timeout'
                    except requests.exceptions.RequestException as e:
                        hook_result = 'exception: %s' % str(e)
                    log_text = "found new location (%s - %u it.) for %s. webhook result: %s" % (loc_str, iter, dev, hook_result)
                else:
                    log_text = 'location did not change. not updating.'

                log.info(log_text)
        else:
            log.debug("Skipping %s" % dev)

    log.info("sleeping %u minutes" % cfg.pause)
    time.sleep(cfg.pause * 60)
