from struct import unpack, pack
from datetime import datetime, timedelta
from time import mktime
import re

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
"This is the format of the exported time stamp when converting to/from ascii."

_ASCII_HEAD = re.compile('^\[([0-9:. -]*)\] ([0-9]*)(?: ([a-z]*))?$')
"For extracting the header info stored in ascii."


def ttyrec2ascii(tty_file, ascii_file, func = None):
    """:param tty_file: ttyrecord binary input file.
:param ascii_file: ascii output file.
:param func: if given will be applied to affect time. it is called with a datetime 
object and expect to return the same object modified if required.
"""
    with open(tty_file, 'rb') as fin:
        with open(ascii_file, 'w') as fout:
            try:
                while True:
                    #extract the header and payload
                    sec, usec, length = unpack(_HEADER, fin.read(_HEADER_SIZE))
                    payload = fin.read(length)
                    
                    #convert
                    dt_stamp = datetime.fromtimestamp(sec) + timedelta(microseconds=usec)
                    #allow some simple time manipulation
                    if func:
                        dt_stamp = func(dt_stamp)
                    fout.write('[%s] %s\n%s\n' % (dt_stamp.strftime(_TIMESTAMP), length, payload))
            except:
                pass        

def ascii2ttyrec(ascii_file, tty_file, func = None):
    """:param ascii_file: ascii input file.
:param tty_file: ttyrecord binary output file.
:param func: if given will be applied to affect time. it is called with a datetime 
object and expect to return the same object modified if required.
"""
    entry_nr=0
    line_nr=0
    with open(ascii_file, 'r') as fin:
        with open(tty_file , 'wb') as fout:
            try:
                offset = timedelta()
                while True:
                    line = fin.readline()
                    entry_nr += 1
                    line_nr += 1
                    if not line: break
                    
                    dt_stamp, length, options = _ASCII_HEAD.match(line).groups()
                    
                    dt_stamp, length = datetime.strptime(dt_stamp, _TIMESTAMP) + offset, int(length)
                    if func:
                        dt_stamp = func(dt_stamp)
                    
                    payload = fin.read(length)
                    line_nr += payload.count('\n')
                    if options:
                        if 'i' in options:
                            step = timedelta(microseconds=20000)
                            #to accomodate first step
                            step_stamp = dt_stamp - step    
                            #this is input we must extend it in a typewritter similar manner
                            for c in payload:
                                step_stamp += step
                                sec, usec = int(mktime(step_stamp.timetuple())), step_stamp.microsecond
                                header = pack(_HEADER, sec, usec, 1)
                                fout.write(header)
                                fout.write(c)
                            assert(fin.read(1)=='\n') #this should be a carriage return
                            line_nr +=1
                            offset += (step_stamp - dt_stamp)
                            continue
                        
                    sec, usec = int(mktime(dt_stamp.timetuple())), dt_stamp.microsecond             
                    header = pack(_HEADER, sec, usec, length)
                    
                    fout.write(header)
                    fout.write(payload)
                    
                    assert(fin.read(1)=='\n') #this should be a carriage return
                    line_nr +=1
            except:
                print "Error in entry %s (line~%s): %s" % (entry_nr, line_nr, line)
                raise        

def ascii2list(ascii_file):
    """:param ascii_file: ascii input file.
:param tty_file: ttyrecord binary output file.
"""
    entry_nr=0
    line_nr=0
    with open(ascii_file, 'r') as fin:
        try:
            offset = timedelta()
            while True:
                line = fin.readline()
                entry_nr += 1
                line_nr += 1
                if not line: break
                
                dt_stamp, length, options = _ASCII_HEAD.match(line).groups()
                
                dt_stamp, length = datetime.strptime(dt_stamp, _TIMESTAMP) + offset, int(length)
                
                payload = fin.read(length)
                line_nr += payload.count('\n')
                if options:
                    if 'i' in options:
                        step = timedelta(microseconds=20000)
                        #to accomodate first step
                        step_stamp = dt_stamp - step    
                        #this is input we must extend it in a typewritter similar manner
                        for c in payload:
                            step_stamp += step
                            yield step_stamp, c
                        assert(fin.read(1)=='\n') #this should be a carriage return
                        line_nr +=1
                        offset += (step_stamp - dt_stamp)
                        continue
                    
                yield dt_stamp, payload
                assert(fin.read(1)=='\n') #this should be a carriage return
                line_nr +=1
        except:
            print "Error in entry %s (line~%s): %s" % (entry_nr, line_nr, line)
            raise 
def ttyrec2list(tty_file, func = None):
    """:param tty_file: ttyrecord binary input file.
:param func: if given will be applied to affect time. it is called with a datetime 
object and expect to return the same object modified if required.
:returns: a generator for a list of (timestamp, payload) values
"""
    with open(tty_file, 'rb') as fin:
        try:
            while True:
                sec, usec, length = unpack(_HEADER, fin.read(_HEADER_SIZE))
                payload = fin.read(length)
                
                #ready
                dt_stamp = datetime.fromtimestamp(sec) + timedelta(microseconds=usec)
                if func:
                    dt_stamp = func(dt_stamp)
                
                yield (dt_stamp, payload)
        except:
            pass  

def list2ttyrec(tty_list, tty_file, func = None):
    """:param tty_list: list input as generated by ttyrec2list.
:param tty_file: ttyrecord binary output file.
:param func: if given will be applied to affect time. it is called with a datetime 
object and expect to return the same object modified if required.
"""
    with open(tty_file , 'wb') as fout:
        for dt_stamp, payload in tty_list:
            length = len(payload)
            if func:
                dt_stamp = func(dt_stamp)
            sec, usec = int(mktime(dt_stamp.timetuple())), dt_stamp.microsecond
            header = pack(_HEADER, sec, usec, length)
            
            fout.write(header)
            fout.write(payload)

