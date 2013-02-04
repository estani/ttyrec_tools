from struct import unpack, pack
from datetime import datetime, timedelta
from inspect import currentframe, getargvalues
import re

from ttyrec.utils import to_datetime, to_timestamp, to_timestamp_tuple, to_timedelta

_HEADER = '<lli'    
"""Each entry of ttyrec is preceded by a 12byte header::

    time_sv (long int sec, long int usec)
    int length

sec: seconds since epoch
usec: microseconds since last second
length: length of the following payload in bytes.
"""

_HEADER_SIZE = 3*4
"3 * 4 (12) bytes"

_TIMESTAMP = '%Y-%m-%d %H:%M:%S.%f'
_TIMESTAMP_OFFSET = '%s.%f'
"This is the format of the exported time stamp when converting to/from ascii."

_ASCII_HEAD = re.compile('^\[([0-9:. -]*)\] ([0-9]*)(?: ([a-z,=.A-Z0-9]*))?$')
"For extracting the header info stored in ascii."

class Options(dict):
    @staticmethod
    def from_str(opt_str):
        parsed_dict = {}
        for opt in opt_str.split(','):
            if '=' in opt:
                key, value = opt.split('=')
            else:
                key, value = opt, None
            parsed_dict[key] = value
        return Options(parsed_dict)
    def add(self, str_val):
        self.update(Options.from_str(str_val))
        
    def __str__(self):
        values = []
        for key, value in self.items():
            if value is None:
                values.append(key)
            else:
                values.append('%s=%s' % (key, value))
        return ','.join(values)     
    
class TTYrecStream(object):
    def __init__(self):
        self._process_pipe = []
        self._gen = None

    def __store(self):
        frame = currentframe(1)
        arg_spec = getargvalues(frame)
        name = frame.f_code.co_name
        args = {}
        for var_name in arg_spec[0] + list(arg_spec[1:3]):
            if var_name and var_name != 'self':
                args[var_name] = arg_spec.locals[var_name]
        self._process_pipe.append((name, args))
        return self
    
    def __reload(self):
        proc_pipe = self._process_pipe
        self._process_pipe = []
        for method, args in proc_pipe:
            getattr(self,method)(**args)
            
    def read_ttyrec(self, tty_file):
        """:param tty_file: ttyrecord binary input file.
    :returns: a generator for a list of (timestamp, payload) values
    """
        def gen():
            with open(tty_file, 'rb') as fin:
                try:
                    while True:
                        sec, usec, length = unpack(_HEADER, fin.read(_HEADER_SIZE))
                        payload = fin.read(length)
                        
                        #ready
                        dt_stamp = to_datetime(seconds=sec, microseconds=usec)
                        
                        yield (dt_stamp, payload, Options())
                except:
                    pass
        self._gen = gen()
        return self.__store()
    
    def read_ascii(self, ascii_file):
        """:param ascii_file: ascii input file."""
        def gen():
            entry_nr=0
            line_nr=0
            start_time = None
            with open(ascii_file, 'r') as fin:
                try:
                    offset = timedelta()
                    while True:
                        line = fin.readline()
                        entry_nr += 1
                        line_nr += 1
                        if not line: break
                        
                        #get strings
                        dt_stamp, length, options = _ASCII_HEAD.match(line).groups()
                        #parse values
                        if start_time:
                            offset += to_timedelta(seconds=float(dt_stamp))
                            dt_stamp = start_time + offset
                        else:
                            start_time = datetime.strptime(dt_stamp, _TIMESTAMP)
                            dt_stamp = start_time
                        length = int(length)
                        if options:
                            options = Options.from_str(options)
                        else:
                            options = Options()
                        
                        payload = fin.read(length)
                        line_nr += payload.count('\n')
                            
                        yield dt_stamp, payload, options
                        assert(fin.read(1)=='\n') #this should be a carriage return
                        line_nr +=1
                except:
                    print "Error in entry %s (line~%s): %s" % (entry_nr, line_nr, line)
                    raise
        self._gen = gen()
        return self.__store()
    
    def write_ascii(self, ascii_file):
        """:param tty_file: ttyrecord binary input file.
    :param ascii_file: ascii output file.
    """
        last_time = None
        if isinstance(ascii_file, basestring):
            fout = open(ascii_file, 'w')
        else:
            fout = ascii_file
        for dt_stamp, payload, options in self._gen:
            #convert
            if last_time is None:
                last_time = dt_stamp
                #first entry retains absolute time
                fout.write('[%s] %s %s\n%s\n' % (last_time.strftime(_TIMESTAMP), len(payload), options, payload))
            else:
                offset = dt_stamp - last_time
                #allow some simple time manipulation
                fout.write('[%s] %s %s\n%s\n' % (to_timestamp(offset), len(payload), options, payload))
            last_time = dt_stamp
            
        #clean
        if isinstance(ascii_file, basestring):
            fout.close()
        #we have consumed the iterator, set it up again
        self.__reload()
        return self
        
    def write_ttyrec(self, tty_file):
        """:param tty_file: ttyrecord binary output file."""
        with open(tty_file , 'wb') as fout:
            offset = timedelta()
            for dt_stamp, payload, options in self._gen:
                length = len(payload)
                if options:
                    if 'i' in options:
                        secs = options['i']
                        if secs is None:
                            secs = 0.1
                        else:
                            secs = float(secs)
                        step = timedelta(microseconds=int(secs * 1000000))
                        #to accommodate first step
                        step_stamp = dt_stamp - step    
                        #this is input we must extend it in a typewritter similar manner
                        for c in payload:
                            step_stamp += step
                            sec, usec = to_timestamp_tuple(step_stamp)
                            header = pack(_HEADER, sec, usec, 1)
                            fout.write(header)
                            fout.write(c)
                        offset += (step_stamp - dt_stamp)
                        #this is already processed, skip
                        continue
                sec, usec = to_timestamp_tuple(dt_stamp)
                header = pack(_HEADER, sec, usec, length)
                
                fout.write(header)
                fout.write(payload)
                
        #we have consumed the iterator, set it up again
        self.__reload()
        return self
        
    #EFFECTS
    def norm_input(self, cpm=350, jitter=0.2, max_delay=1, cap_to_max=False):
        """Normalizes input to the given CPM (characters per minute) speed.
    :param tty_list: a ttyrec list.
    :param cpm: characters per minute for the desired output."""
        def gen(old_generator):
            norm_char_time = timedelta(microseconds=60.0 * 1000000.0 / cpm)
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
            for tstamp, payload, options in old_generator:
                if last_tstamp and len(payload) == 1:
                    char_time = to_timedelta(jitter_func(to_timestamp(norm_char_time)))
                    #this is the type of input we care for normalization
                    offset += char_time - (tstamp - last_tstamp)
                
                yield tstamp + offset, payload, options
                last_tstamp = tstamp
                
        self._gen = gen(self._gen)
        return self.__store()
    
    def cap_delays(self, max_delay=3):
        """Reduces all delay to the given maximum.
    
    :param tty_list: a ttyrec list.
    :param max_delay: maximal number of seconds to wait between any kind of feedback (i.e. input or output)."""
        def gen(old_generator):
            last_tstamp = datetime.now()
            offset = timedelta()
            for tstamp, payload, options in old_generator:
                elapsed_time = to_timestamp(tstamp - last_tstamp)
                if last_tstamp and elapsed_time > max_delay:
                    offset += to_timedelta(max_delay - elapsed_time)
                
                yield tstamp + offset, payload, options  
                last_tstamp = tstamp
        self._gen = gen(self._gen)
        return self.__store()
    
    def change_speed(self, speed=1):
        """changes the recorded speed to the given one.
    
    :param tty_list: a ttyrec list.
    :param speed: speed factor (<1 = slower, >1 = faster)."""
        def gen(old_generator):
            last_tstamp = None
            offset = timedelta()
            for tstamp, payload, options in old_generator:
                if last_tstamp:
                    elapsed_time = to_timestamp(tstamp - last_tstamp)
                    offset += to_timedelta((elapsed_time / speed)- elapsed_time)
                    
                    yield tstamp + offset, payload, options
                last_tstamp = tstamp
        self._gen = gen(self._gen)
        return self.__store()
    
    def add_intro(self, intro_delay=1):
        """Clears the screen before starting and remain like that for a while.
    
    :param tty_list: a ttyrec list.
    :param intro_delay: number of seconds (or fraction) to remain with the screen black."""
        def gen(old_generator):
            show_intro = True
            clear_screen = '\x1b[H\x1b[2J'
            
            for tstamp, payload, options in old_generator:
                if show_intro:
                    show_intro = False
                    yield tstamp - timedelta(seconds=intro_delay), clear_screen, Options()
                    
                yield tstamp, payload, options
        self._gen = gen(self._gen)
        return self.__store()
    
    def delay_lines(self, delay_per_line=0.1):
        """Break lines stored and show them with some delay, line by line.
        
    :param tty_list: a ttyrec list.
    :param delay_per_line: seconds (or fraction) to wait between lines"""
        def gen(old_generator):
            delay = timedelta(microseconds=delay_per_line * 1000000)
            offset = timedelta()
            for tstamp, payload, options in old_generator:
                first=True
                for line in payload.splitlines(True):
                    if first:
                        first=False
                    else:
                        offset += delay    
                    yield tstamp + offset, line, options
        self._gen = gen(self._gen)
        return self.__store()
    
    def delay_input(self, delay_before_input=0, delay_after_input=1):
        """Adds some delay before nand/or after the input is done.
        
    :param tty_list: a ttyrec list.
    :param delay_before_input: seconds (or fraction) to wait before input starts.
    :param delay_after_input: seconds (or fraction) to wait after input finishes."""
        def gen(old_generator):
            delay_before = timedelta(microseconds=delay_before_input * 1000000)
            delay_after = timedelta(microseconds=delay_after_input * 1000000)
            offset = timedelta()
            in_input = False
            last_stamp = None
            for tstamp, payload, options in old_generator:
                if 'i' in options:
                    if not in_input:
                        offset += delay_before
                        in_input = True
                elif in_input:
                    offset += delay_after
                    in_input = False
                new_stamp = tstamp + offset
                if last_stamp and new_stamp < last_stamp:
                    #correct
                    offset +=  tstamp + offset - last_stamp
                    new_stamp = last_stamp
                yield new_stamp, payload, options
                last_stamp = tstamp + offset
        self._gen = gen(self._gen)
        return self.__store()
    
    def merge_lines(self, threshold=0.01):
        def gen(old_generator):
            last_entry = [to_datetime(0), None, None]
            carry = False
            for tstamp, payload, options in old_generator:
                if to_timestamp(tstamp - last_entry[0]) < threshold and last_entry[1] is not None:
                    #we preserve the options from the first entry
                    last_entry[1] += payload
                    carry = True
                    continue
                elif carry:
                    carry = False
                if last_entry[1] is not None:
                    #wait until the buffer is full
                    yield last_entry[0],last_entry[1],last_entry[2]
                last_entry = [tstamp, payload, options]
            #flush the buffer
            if last_entry[1] is not None:
                yield last_entry[0],last_entry[1],last_entry[2]
        self._gen = gen(self._gen)
        return self.__store()
    
    def mark_input(self, prompt_suffix=' $ '):
        def gen(old_generator):
            next_is_input = False
            for dt_stamp, payload, options in old_generator:
                if next_is_input:
                    next_is_input = False
                    options.add('i')
                elif prompt_suffix and payload.endswith(prompt_suffix):
                    next_is_input = True
                yield dt_stamp, payload, options
        self._gen = gen(self._gen)
        return self.__store()
        
    
        
