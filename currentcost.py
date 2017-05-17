#!/usr/bin/env python

import datetime
import serial
from xml.etree.cElementTree import fromstring
import signal
import sys
import time
import os
import requests

EXAMPLE_LINE = '<msg><src>CC128-v1.48</src><dsb>00789</dsb><time>22:20:42</time><tmpr>22.7</tmpr><sensor>0</sensor><id>02872</id><type>1</type><ch1><watts>00500</watts></ch1></msg>\r\n'  # noqa


def main(argv):
    if len(argv) > 1 and argv[1] == '--fake':
        serial_class = FakeSerial
        serial_args = []
    else:
        serial_class = serial.Serial
        serial_args = ('/dev/ttyUSB0', 57600)

    signal.signal(signal.SIGTERM, signal_term_handler)

    with serial_class(*serial_args) as s:
        try:
            while True:
                watts = parse_watts(s.readline())

                if watts is not None:
                    upload_reading((utc_now(), watts))

        except KeyboardInterrupt:
            pass


class UTC(datetime.tzinfo):
    def utcoffset(self, dt):
        return datetime.timedelta(0)

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return datetime.timedelta(0)


class FakeSerial(object):
    def __init__(self, reading_every_seconds=6):
        self.next_reading = datetime.datetime.now()
        self.reading_every_seconds = reading_every_seconds

    def __enter__(self, *args, **kwargs):
        return self

    def __exit__(self, *args, **kwargs):
        pass

    def readline(self):
        seconds_till_next_reading = (
            self.next_reading - datetime.datetime.now()
        ).total_seconds()

        if seconds_till_next_reading > 0:
            time.sleep(seconds_till_next_reading)

        self.next_reading += datetime.timedelta(
            seconds=self.reading_every_seconds)

        return EXAMPLE_LINE


def utc_now():
    return datetime.datetime.now(UTC())


def utc_epoch_time(utc_datetime):
    return (
        utc_datetime - datetime.datetime(1970, 1, 1, tzinfo=UTC())
    ).total_seconds()


def parse_watts(line):
    if not line:
        raise ValueError('Time out')

    xml = fromstring(line)

    if xml.tag != 'msg':
        return

    if xml.find('hist'):
        return

    watts = int(xml.find('ch1').find('watts').text)
    return watts


def signal_term_handler(signal, frame):
    sys.exit(0)


def upload_reading(reading):
    dt, watts = reading

    url = make_emoncms_url(dt, watts)
    # print(url)

    try:
        response = requests.post(url)
        response.raise_for_status()
        assert response.text == 'ok', response.text
    except Exception as e:
        print(e)
        return False
    else:
        return True


def make_emoncms_url(dt, watts):
    return '{emoncms_url}/input/post.json?time={timestamp}&node={node}&json={{{input_name}:{watts}}}&apikey={api_key}'.format(  # noqa
        timestamp=utc_epoch_time(dt),
        emoncms_url=os.environ['EMONCMS_URL'],
        input_name=os.environ['EMONCMS_INPUT_NAME'],
        watts=watts,
        node=os.environ['EMONCMS_NODE'],
        api_key=os.environ['EMONCMS_API_KEY']
    )


if __name__ == '__main__':
    main(sys.argv)
