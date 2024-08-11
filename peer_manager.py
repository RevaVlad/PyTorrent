import math
import asyncio
import bitstring
from block import Block
from math import ceil


class PeerManager:

    def __init__(self, peer, torrent_data):
        self.torrent_data = torrent_data
        self.peer = peer
        self._working_segment = -1

        self.peer.events.on_requesting_segment += self.upload_segment
        self.peer.events.on_receiving_block += self.on_get_block

        self.downloaded_blocks = []
        self.pending_blocks = []
        self.missing_blocks = asyncio.Queue()

    def close(self):
        self.peer.close()

    def check_available_segments(self):
        return self.peer.available_files

    async def download_segment(self, segment_id):
        if self._working_segment == -1:
            return False
        self._working_segment = segment_id

        segment_length = self.torrent_data.segment_length if segment_id != self.torrent_data.total_segments - 1 \
            else self.torrent_data.total_length % self.torrent_data.segment_length

        total_blocks = ceil(segment_length / Block.BLOCK_LENGTH)
        for block_offset in range(0, (total_blocks - 1) * Block.BLOCK_LENGTH, Block.BLOCK_LENGTH):
            self.missing_blocks.put_nowait(Block(segment_id, block_offset))
        self.missing_blocks.put_nowait(Block(segment_id, segment_length % Block.BLOCK_LENGTH))

        while len(self.downloaded_blocks) < total_blocks:
            pass


    def on_get_block(self, block):
        self.pending_blocks.remove(block)
        self.downloaded_blocks.append(block)

    async def upload_segment(self):
        pass