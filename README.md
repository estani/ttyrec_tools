ttyrec_tools
============

ttyrec tools for python. Just a set of tools for handling ttyrec files.
This are rough functions designed to just do the work, though the more I need them, the more
time I'll put into getting a nice piece of code out of it.


Packages:

* io: handles reading and writing. (Can read/write to/from ascii for simple edition)
 * ascii format also has some mark-ups for signaling how to process the data:
  - i: type-write what follows (to mark cut&pasted input as being written by hand) 
* effects: different effects like:
 * change speed
 * cap delays
 * normalize typing
 * humanize typing 

All implemented effects (and io) work as generators so you can chain them and 
work in very large files.

