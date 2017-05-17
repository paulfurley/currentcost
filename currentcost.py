#!/usr/bin/env python

import collections
import datetime
import json
import io
import serial
from xml.etree.cElementTree import fromstring
import signal
import sys
import time
import logging

from os.path import dirname, join as pjoin

import requests

EXAMPLE_LINE = '<msg><src>CC128-v1.48</src><dsb>00789</dsb><time>22:20:42</time><tmpr>22.7</tmpr><sensor>0</sensor><id>02872</id><type>1</type><ch1><watts>00500</watts></ch1></msg>\r\n'  # noqa
MAX_BUFFER_LENGTH = 14400  # 24 hours @ 1 reading per 6 seconds

SESSION = requests.Session()


def main(argv):
    load_settings()
    logging.basicConfig(
        level=logging.DEBUG if SETTINGS['DEBUG'] else logging.INFO
    )

    if SETTINGS['FAKE_MODE']:
        serial_class = FakeSerial
        serial_args = []
    else:
        serial_class = serial.Serial
        serial_args = ('/dev/ttyUSB0', 57600)

    signal.signal(signal.SIGTERM, signal_term_handler)

    readings_buffer = collections.deque(maxlen=MAX_BUFFER_LENGTH)
    with serial_class(*serial_args) as s:
        try:
            while True:
                watts = parse_watts(s.readline())

                if watts is not None:
                    readings_buffer.append((utc_now(), watts))  # to *right*
                    upload_readings(readings_buffer)

        except KeyboardInterrupt:
            pass


def load_settings():
    global SETTINGS

    with io.open(pjoin(dirname(__file__), 'settings.json'), 'rt') as f:
        SETTINGS = json.load(f)


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


def upload_readings(queue, for_seconds=5):
    """
    left --> [oldest_reading, ..., newest_reading]  <-- right

    always *add* to right and *take* from left
    """

    stop_at = datetime.datetime.now() + datetime.timedelta(seconds=for_seconds)

    while datetime.datetime.now() < stop_at:
        if len(queue) > 1:
            logging.info('{} reading(s) in queue'.format(len(queue)))
        else:
            logging.debug('{} reading(s) in queue'.format(len(queue)))

        try:
            oldest_reading = queue.popleft()
        except IndexError:  # no more readings
            return

        try:
            upload_reading(oldest_reading)
        except Exception as e:
            logging.exception(e)
            queue.appendleft(oldest_reading)
            break


def upload_reading(reading):
    dt, watts = reading

    url = make_emoncms_url(dt, watts)
    logging.debug(url)

    response = SESSION.post(url, timeout=4)
    response.raise_for_status()
    assert response.text == 'ok', response.text


def make_emoncms_url(dt, watts):
    return '{emoncms_url}/input/post.json?time={timestamp}&node={node}&json={{{input_name}:{watts}}}&apikey={api_key}'.format(  # noqa
        timestamp=utc_epoch_time(dt),
        emoncms_url=SETTINGS['EMONCMS_URL'],
        input_name=SETTINGS['EMONCMS_INPUT_NAME'],
        watts=watts,
        node=SETTINGS['EMONCMS_NODE'],
        api_key=SETTINGS['EMONCMS_API_KEY']
    )


if __name__ == '__main__':
    main(sys.argv)
