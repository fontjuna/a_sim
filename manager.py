from public import gm
import logging

class Manager:
    def __init__(self):
        self.name = 'man'
        
        self.init()

    def init(self):
        logging.debug(f'{self.name} init')

