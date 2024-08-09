from abc import ABC, abstractmethod
from struct import pack, unpack
import logging
import bitstring


class Message(ABC):
    @abstractmethod
    def encode(self):
        pass

    @staticmethod
    @abstractmethod
    def decode(message):
        pass


class Handshake(Message):
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


class Interested(Message):
    """
    <0001><2>
    """
    def encode(self):
        return pack('!IB', 1, 2)

    @staticmethod
    def decode(message):
        data_length, message_id = unpack('!IB', message)
        if message_id != 2:
            logging.error(f'При запросе на интерес был получен некорректный индентификатор: {message_id}')
        return Interested()


class Choked(Message):
    """
    <0001><1>
    """
    def encode(self):
        return pack('!IB', 1, 1)

    def decode(self, message):
        data_length, message_id = unpack('!IB', message)
        if message_id != 1:
            logging.error(f'При запросе на снятие заглушки был получен некорректный индентификатор: {message_id}')
        return Choked()
