import logging
import bitstring


class Peer:

    def __init__(self, ip, number_of_pieces, port, file_writer):
        self.file_writer = file_writer
        self.last_call = 0.0
        self.has_handshaked = False
        self.healthy = False
        self.read_buffer = b''
        self.socket = None
        self.ip = ip
        self.port = port
        self.number_of_pieces = number_of_pieces
        self.state = {
            'am_choking': True,
            'am_interested': False,
            'peer_choking': True,
            'peer_interested': False,
        }

    def __hash__(self):
        return "%s:%d" % (self.ip, self.port)

    def connect(self):
        return False

    async def send_block(self, segment_id):
        segment = await self.file_writer.read_segment(segment_id)
