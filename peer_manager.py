import math
import asyncio
import bitstring


class PeerManager:

    def __init__(self, torrent, tracker_manager, segment_writer, torrent_statistics):
        self.pending_blocks = []
        self.retrieved_blocks = []
        self.missing_blocks = []

        total_segments_number = math.ceil(torrent.total_length / torrent.segment_length)
        self.have = bitstring.BitArray(length=total_segments_number)

        self.blocks_queue = asyncio.Queue()