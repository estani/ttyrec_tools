from struct import unpack, pack
from datetime import datetime, timedelta
from inspect import currentframe, getargvalues
import re
import os

from ttyrec.utils import to_datetime, to_timestamp, to_timestamp_tuple, to_timedelta

_HEADER = '<lli'    
"""Each entry of ttyrec is preceded by a 12byte header::

    time_sv (long int sec, long int usec)
    int length

sec: seconds since epoch
usec: microseconds (since last second :-)
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

class Stream(object):
    """Handle any string pointing to a path or any other similar object and close
only if required (i.e. if it was opened here)"""
    def __init__(self, path, *opts):
        if isinstance(path, basestring):
            path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
            self.stream = open(path, *opts)
            self.closeOnExit = True
        else:
            #don't close anything it wasn't opened here.
            self.stream = path
            self.closeOnExit = False
    def __enter__(self):
        return self.stream
    def __exit__(self, exc_type, value, traceback):
        if self.closeOnExit:
            self.stream.close()
            
class TTYrecStream(object):
    """This objects encapsulates all handling of ttyrec files and their ascii representation.
It works also as a generator so you can iterate the results as may times as required.
The operations applied are stored and reapplied every time the generator is run.
This means that no access is being done until required, each element is accessed only once
and on demand.
All methods return the object itself to easy concatenation. This is an example::

    from ttyrec.io import TTYrecStream
    
    #load a file and add some intro (file is not being read at this time)
    basic = TTYrecStream.load_ttyrec('/tmp/a_file').add_intro(intro_delay=2)
    
    #print the first five entries without ever accessing all the file
    import itertools
    print list(itertools.islice(basic, 0 , 5))
    
    #continue processing
    basic.mark_input().delay_input(delay_after_input=2.5)
    
    #write the file without every getting all the file to memory
    basic.write_ascii('/tmp/ascii_repr')

There is no buffer strategy in place besides the default system stratgegy for handling the "open" call.
defining this would be very simple. 
"""
    def __init__(self):
        """Prepare the process pipe and the empty generator"""
        self._process_pipe = []
        self._gen = None

    def __store(self):
        """Store the method being called for re-play."""
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
        """Reloads the configuration to setup the generator again."""
        proc_pipe = self._process_pipe
        self._process_pipe = []
        for method, args in proc_pipe:
            getattr(self,method)(**args)

    def __iter__(self):
        """Returns the setup iterator and prepare a new one"""
        it = self._gen
        self.__reload()
        return it
    
    def read_ttyrec(self, tty_file):
        """Reads a ttyrec binary file.

:param tty_file: ttyrecord binary input file.
:returns: This object"""
        def gen():
            with Stream(tty_file, 'rb') as fin:
                try:
                    while True:
                        sec, usec, length = unpack(_HEADER, fin.read(_HEADER_SIZE))
                        payload = fin.read(length)
                        
                        #ready
                        dt_stamp = to_datetime(seconds=sec, microseconds=usec)
                        
                        yield dt_stamp, payload, Options()
                except:
                    pass
        self._gen = gen()
        return self.__store()
    
    def read_ascii(self, ascii_file):
        """Reads an ascii file representing a ttyrec binary.

:param ascii_file: ascii input file.
:returns: This object"""
        def gen():
            entry_nr=0
            line_nr=0
            start_time = None
            with Stream(ascii_file, 'r') as fin:
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
                        assert(fin.read(1)=='\n') #There should be a carriage return separating each entry
                        line_nr +=1
                except:
                    print "Error in entry %s (line~%s): %s" % (entry_nr, line_nr, line)
                    raise
        self._gen = gen()
        return self.__store()
    
    def write_ascii(self, ascii_file):
        """Writes result to an ascii file.

:param ascii_file: ascii output file.
    """
        last_time = None
        with Stream(ascii_file, 'w') as fout:
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
            
        #we have consumed the iterator, set it up again
        self.__reload()
        return self
        
    def write_ttyrec(self, tty_file):
        """Writes result to a ttyrec binary file that can be replayed with ttyplay.
        
:param tty_file: ttyrecord binary output file."""
        
        from random import Random
        r = Random(0)
        def jitter_func(time, jitter=None, max_delay=None, cap_to_max=None):
            if jitter is None: jitter = 0.02
            if max_delay is None: max_delay = 1
            if cap_to_max is None: cap_to_max = True
            res = r.random()
            if res < 0.5:
                return time * (res * 2 * jitter + (1-jitter))
            elif time > max_delay:
                if cap_to_max: return max_delay
                else: return time
            else:
                res = (res - 0.5) * 2 * jitter
                return (max_delay - time) * res + time

        with Stream(tty_file , 'wb') as fout:
            offset = timedelta()
            for dt_stamp, payload, options in self._gen:
                length = len(payload)
                if options:
                    if 'i' in options:
                        secs = options['i']
                        if secs is None: secs = 0.1
                        else: secs = float(secs)
                        jitter = options.get('j', None)
                        if jitter is not None: jitter = float(jitter)
                        norm_char_time = timedelta(seconds=secs)
                        
                        #to accommodate first step
                        step = timedelta(0)
                        step_stamp = dt_stamp    
                        #this is input we must extend it in a typewritter similar manner
                        for c in payload:
                            step_stamp += step
                            sec, usec = to_timestamp_tuple(step_stamp + offset)
                            header = pack(_HEADER, sec, usec, 1)
                            fout.write(header)
                            fout.write(c)
                            step = to_timedelta(jitter_func(to_timestamp(norm_char_time), jitter))
                        offset += (step_stamp - dt_stamp)
                        #this is already processed, skip
                        continue
                sec, usec = to_timestamp_tuple(dt_stamp + offset)
                header = pack(_HEADER, sec, usec, length)
                
                fout.write(header)
                fout.write(payload)
                
        #we have consumed the iterator, set it up again
        self.__reload()
        return self
        
    #EFFECTS
    def cap_delays(self, max_delay=3):
        """Reduces all delay to the given maximum.
    
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
        """Adds some delay before and/or after the input is done.
        
:param delay_before_input: seconds (or fraction) to wait before input starts.
:param delay_after_input: seconds (or fraction) to wait after input finishes."""
        def gen(old_generator):
            delay_before = timedelta(microseconds=delay_before_input * 1000000)
            delay_after = timedelta(microseconds=delay_after_input * 1000000)
            offset = timedelta()
            in_input = False
            last_stamp = None
            for tstamp, payload, options in old_generator:
                if last_stamp is not None:
                    elapsed = tstamp - last_stamp
                    if 'i' in options:
                        if not in_input:
                            offset +=  delay_before - elapsed
                            in_input = True
                    elif in_input:
                        offset += delay_after - elapsed 
                        in_input = False
                yield tstamp + offset, payload, options
                last_stamp = tstamp
        self._gen = gen(self._gen)
        return self.__store()
    
    def raw_effect(self, func=None):
        if func is not None:
            def gen(old_generator):
                for tstamp, payload, options in old_generator:
                    yield func(tstamp, payload, options)
        self._gen = gen(self._gen)
        return self.__store()
    def effect(self, generator):
        self._gen = generator(self._gen)
        return self.__store()
    
    def merge_lines(self, threshold=0.01, merge_input=False):
        """Merge lines with less than threshold seconds pause together."""
        def gen(old_generator):
            last_entry = [to_datetime(0), None, None]
            carry = False
            for tstamp, payload, options in old_generator:
                if to_timestamp(tstamp - last_entry[0]) < threshold and last_entry[1] is not None \
                        and ('i' not in options or merge_input):
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
        """Mark lines following what is defined to be the end of the prompt as input 
(if not already marked as such)"""
        def gen(old_generator):
            next_is_input = False
            for dt_stamp, payload, options in old_generator:
                if next_is_input:
                    next_is_input = False
                    if 'i' not in options: options.add('i')
                elif prompt_suffix and payload.endswith(prompt_suffix):
                    next_is_input = True
                yield dt_stamp, payload, options
        self._gen = gen(self._gen)
        return self.__store()
        
        
from time import sleep
import curses
import sys
class Player(object):
    def __init__(self, stream = None):
        if stream is None:
            stream = TTYrecStream()
        self._stream = stream
        
    def load(self, tty_file):
        self._stream.read_ttyrec(tty_file)
    
    def play(self, speed=1.0):
        try:
            w = curses.initscr()
            w.nodelay(True)
            curses.noecho()
            start = datetime.now()
            first = None
            last = None
            offset = timedelta()
            running = True
            for tstamp, entry, _ in self._stream:
                try:
                    while True:
                        #we consume all events before proceeding
                        #to avoid processing old signals
                        key = w.getch()
                        if key == curses.ERR:
                            #all events has been consumed
                            break                
                        if key == ord('q'):
                            running=True
                        elif key in map(ord, 'p '):
                            pause_start = datetime.now()
                            w.nodelay(False)
                            while True:
                                key = w.getkey()
                                if key in 'p ': 
                                    break
                            offset += datetime.now() - pause_start
                            w.nodelay(True)
                        elif key == ord('f'):
                            if speed < 10:
                                speed *= 2.0
                        elif key == ord('s'):
                            if speed > 0.01:
                                speed /= 2.0
                        elif key == ord('0'):
                            speed = 0.5
                        elif key >= ord('1') and key <= ord('9'):
                            speed = float(key - ord('0'))
                            
                except:
                    pass
                if not running:
                    break
                if last:
                    offset += to_timedelta(seconds=to_timestamp(tstamp-last) / speed)
                    sleep(to_timestamp((start + offset) - datetime.now()))
                else:
                    first = tstamp
                sys.stdout.write(entry)
                sys.stdout.flush() 
                last = tstamp
            recording_time=last-first
            play_time=offset
        finally:
            curses.endwin()

        print "Recording: %s" % recording_time
        print "Play time: %s" % play_time

            