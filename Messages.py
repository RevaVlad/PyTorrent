from abc import ABC, abstractmethod, abstractstaticmethod
from struct import pack, unpack


class Messages(ABC):
    @abstractmethod
    def encode(self):
        pass

    @abstractstaticmethod
    def decode(message):
        pass


class Handshake(Messages):
    """
    <19><BitTorrent protocol><0x0000000000000000><info_hash><peer_id>
    """
    def __init__(self, info_hash: bytes, peer_id):
        self.info_hash = info_hash
        self.peer_id = peer_id

    def encode(self):
        return pack(f'!B19s8s20s20s', 19, 'BitTorrent protocol', b'\x00' * 8, self.info_hash, self.peer_id)

    @staticmethod
    def decode(message):
        identifier_length, identifier, reserved, info_hash, peer_id = unpack('!B19s8s20s20s', message)
        return Handshake(info_hash, peer_id)
