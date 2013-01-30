
from datetime import datetime, timedelta
from ttyrec.utils import to_timestamp, to_timedelta

def norm_input(tty_list, cpm=350):
    """Normalizes input to the given CPM (characters per minute) speed.
:param tty_list: a ttyrec list.
:param cpm: characters per minute for the desired output."""
    microsec_per_char = 60.0*1000000.0/cpm
    char_time = timedelta(microseconds=microsec_per_char)
    last_tstamp = None
    offset = timedelta()
    for tstamp, payload in tty_list:
        if len(payload) == 1:
            #this is the type of input we care for normalization
            offset += char_time - (tstamp - last_tstamp)
        
        yield tstamp + offset, payload    
        last_tstamp = tstamp

def humanize_input(tty_list, jitter=0.2, max_delay=1, cap_to_max=False):
    """Apply some jitter to input (i.e. une char entries) so it looks more natural.
Value will be in [0, max_delay] range and jitter from original.

:param tty_list: a ttyrec list.
:param jitter: amount of jitter to apply. 
:param max_delay: maximum number of secs (accepts fraction) when jitter is positive."""
    from random import Random
    r = Random(0)
    def jitter_func(time):
        res = r.random()
        if res < 0.5:
            return time * (res * 2 * jitter + (1-jitter))
        elif time > max_delay:
            if cap_to_max: return max_delay
            else: return time
        else:
            res = (res - 0.5) * 2 * jitter
            return (max_delay - time) * res + time
    
    last_tstamp = None
    offset = timedelta()
    for tstamp, payload in tty_list:
        if last_tstamp and len(payload) == 1:
            char_time = to_timedelta(jitter_func(to_timestamp(tstamp - last_tstamp)))
            #this is the type of input we care for normalization
            offset += char_time - (tstamp - last_tstamp)
        
        yield tstamp + offset, payload    
        last_tstamp = tstamp

def cap_delays(tty_list, max_delay=3):
    """Reduces all delay to the given maximum.

:param tty_list: a ttyrec list.
:param max_delay: maximal number of seconds to wait between any kind of feedback (i.e. input or output)."""
    last_tstamp = datetime.now()
    offset = timedelta()
    for tstamp, payload in tty_list:
        elapsed_time = to_timestamp(tstamp - last_tstamp)
        if last_tstamp and elapsed_time > max_delay:
            offset += to_timedelta(max_delay - elapsed_time)
        
        yield tstamp + offset, payload    
        last_tstamp = tstamp

def change_speed(tty_list, speed=1):
    """changes the recorded speed to the given one.

:param tty_list: a ttyrec list.
:param speed: speed factor (<1 = slower, >1 = faster)."""
    last_tstamp = None
    offset = timedelta()
    for tstamp, payload in tty_list:
        if last_tstamp:
            elapsed_time = to_timestamp(tstamp - last_tstamp)
            offset += to_timedelta((elapsed_time / speed)- elapsed_time)
            
            yield tstamp + offset, payload    
        last_tstamp = tstamp

ttyrec.io.list2ttyrec(change_speed(ttyrec.io.ttyrec2list('/tmp/ttytest'),speed=5), '/tmp/ttytest4')

lgen_new = norm_input(tty_list)
ttyrec.io.list2ttyrec(norm_input(ttyrec.io.ttyrec2list('/tmp/ttytest')), '/tmp/ttytest2')
ttyrec.io.list2ttyrec(humanize_input(norm_input(ttyrec.io.ttyrec2list('/tmp/ttytest'), cpm=800), jitter=0.3, max_delay=0.5), '/tmp/ttytest3')
ttyrec.io.list2ttyrec(cap_delays(ttyrec.io.ttyrec2list('/tmp/ttytest')), '/tmp/ttytest4')
ttyrec.io.list2ttyrec(change_speed(ttyrec.io.ttyrec2list('/tmp/ttytest'),speed=5), '/tmp/ttytest4')


ttyrec.io.ttyrec2ascii('/tmp/ttytest3', '/tmp/ttytest3.ascii')
