ttyrec_tools
============

ttyrec tools for python. Just a set of tools for handling ttyrec files.

Packages:

* io: handles reading and writing. (Can read/write to/from ascii for simple edition)
* effects: different effects like:
 * cahnge speed
 * cap delays
 * normalize typing
 * humanize typing 

All implemented effects (and io) work as generators so you can chain them and 
work in very large files.

