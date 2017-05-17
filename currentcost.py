#!/usr/bin/env python

import datetime
import serial
from xml.etree.cElementTree import fromstring
import time
import csv
import signal
import sys


class UTC(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return datetime.timedelta(0)


def utc_now_string():
    return datetime.datetime.now(UTC()).strftime('%Y-%m-%dT%H:%M:%SZ')


def parse_watts(serial_line):
    xml = fromstring(serial_line)

    if xml.tag != 'msg':
        return

    if xml.find('hist'):
        return

    watts = int(xml.find('ch1').find('watts').text)
    return watts


serial = serial.Serial('/dev/ttyUSB0', 57600)

with open('/srv/currentcost/currentcost.csv', 'a') as csvfile:
    writer = csv.writer(csvfile)

    def signal_term_handler(signal, frame):
        csvfile.flush()
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_term_handler)

    try:
        while True:
            msg = serial.readline()
            if not msg:
                raise ValueError('Time out')

            watts = parse_watts(msg)
            if watts is None:
                continue

            timestamp = utc_now_string()

            row = [timestamp, watts]
            writer.writerow(row)

    except KeyboardInterrupt:
        csvfile.flush()
