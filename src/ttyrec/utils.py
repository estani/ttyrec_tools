from datetime import datetime, timedelta
from time import mktime
def to_datetime(seconds=0, microseconds=0):
    return datetime.fromtimestamp(seconds) + timedelta(microseconds=microseconds)

def to_timedelta(seconds=0, microseconds=0):
    return timedelta(seconds=seconds) + timedelta(microseconds=microseconds)

def to_timestamp(dt_object):
    if isinstance(dt_object, timedelta):
        dt_object = datetime.fromtimestamp(0) + dt_object
    return int(mktime(dt_object.timetuple())) + dt_object.microsecond / 1000000.0
