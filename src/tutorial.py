'''
Created on 08.02.2013

@author: estani
'''
import os
import logging
log = logging.getLogger(__name__)

from glob import glob
from evaluation_system.api import plugin
from ttyrec.io import Player

class Tutorials(plugin.PluginAbstract):
    __short_description__ = "Display some tutorials." 
    __version__ = (0,0,1)
    __config_metadict__ =  plugin.metadict(compact_creation=True,
                            tutorial = (None, dict(mandatory=True, type=str, help='The tutorial to be displayed')))

    def getHelp(self):
        path_to_this_file = self.getClassBaseDir()
        return '%s\nList of available tutorials:\n\t%s' % (super(Tutorials,self).getHelp(),
            '\n\t'.join(os.listdir('%s/recordings' % path_to_this_file)))
        
    def runTool(self, config_dict=None):
        path_to_this_file = self.getClassBaseDir()
        tutorial = config_dict['tutorial']
        tut_path = glob('%s/recordings/%s' % (path_to_this_file, tutorial))
        if len(tut_path) >1:
            raise Exception("Your input resulted in multiple tutorials: %s\nPlease select one" % ', '.join(tut_path))
        elif len(tut_path) == 1:
            tut_path = tut_path[0]
        log.debug("Trying to load file %s", tut_path)
        if tut_path and os.path.isfile(tut_path):
            p = Player()
            p.load(tut_path)
            p.play()
        else:
            raise Exception("File %s found." % tutorial)
