"""This effects are thought as examples of what can be used for the raw_effect
They would be used like::

    TTYrecStream().read_ascii('file.ascii').delay_lines(delay_per_line=0.05).raw_effect(
        LinearInputDelay(start_delay=0.1, end_delay=0.01, duration=600).linear_delay)\
        .write_ascii('/tmp/test1.ascii')

"""
from ttyrec.utils import to_timestamp

class LinearInputDelay(object):
    def __init__(self, start_delay=0.1, end_delay=0.01, duration=600):
        self.start_delay = start_delay
        self.end_delay = end_delay
        self.duration = duration
        self.start = None
        self.last = None
    def linear_delay(self, tstamp, payload, options):
        if self.start is None:
            self.start = tstamp
        else:
            if 'i' in options:
                #just interpolate linearly between the two values
                if tstamp < self.last:
                    print self.last, tstamp, repr(payload), options
                factor = min(to_timestamp(tstamp - self.start), self.duration)/self.duration
                options['i']= self.start_delay * (1 - factor) + self.end_delay * factor
        self.last = tstamp
        return tstamp, payload, options

def RemoveWindowSize(generator):
    import re
    cr = re.compile(r' \r(:?[^\n]|$)')
    for items in generator:
        #tstamp, payload, options = items[:3]
        items = [items[0], cr.sub(r'\1', items[1])] + list(items[2:])
        yield tuple(items)