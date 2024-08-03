import math
import asyncio
import bitstring
'''
from enum import Enum


class PeerStatus(Enum):
    DOWNLOADING = 'downloading'
    COMPLETED = 'completed'
'''


class PeerManager:

    def __init__(self, peer):
        # self.status = PeerStatus.WAITING
        self.working_segment = -1
        self.blocks_queue = asyncio.Queue()
