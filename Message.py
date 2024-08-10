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


class PeerSegments(Message):
    """
    <segments_length + 1><5><segments_like_bytes>
    """

    def __init__(self, segments: bitstring.BitArray):
        self.segments = segments
        self.segments_like_bytes = segments.tobytes()

    def encode(self):
        return pack(f'!IB{len(self.segments_like_bytes)}s', len(self.segments_like_bytes) + 1, 5,
                    self.segments_like_bytes)

    @staticmethod
    def decode(message):
        message_length, message_id = unpack('!IB', message[:5])
        segments = unpack(f'!{message_length - 1}s', message[5:])
        return PeerSegments(bitstring.BitArray(bytes=segments))


class RequestsMessage(Message):
    """
    <0013><6><index><byte_offset><block_len>
    """

    def __init__(self, index: int, byte_offset: int, block_len: int):
        self.index = index
        self.byte_offset = byte_offset
        self.block_len = block_len

    def encode(self):
        return pack('!IBIII', 13, 1, self.index, self.byte_offset, self.block_len)

    @staticmethod
    def decode(message):
        message_length, message_id, index, byte_offset, block_len = unpack('!IBIII', message)
        return RequestsMessage(index, byte_offset, block_len)


class SendPiece(Message):
    """
    <9 + len(data)><7><index><byte_offset><data>
    """

    def __init__(self, index: int, byte_offset: int, data):
        self.index = index
        self.byte_offset = byte_offset
        self.data = data

    def encode(self):
        return pack(f'!IBII{len(self.data)}s', 9 + len(self.data), 7, self.index, self.byte_offset, self.data)

    @staticmethod
    def decode(message):
        message_length, message_id = unpack('!IB', message[:5])
        index, byte_offset, data = unpack(f'!II{message_length - 9}s', message[5:])
        return SendPiece(index, byte_offset, data)


class PeersPieces(Message):
    """
    <0005><4><piece_index>
    """

    def __init__(self, piece_index):
        self.piece_index = piece_index

    def encode(self):
        return pack('!IBI', 5, 4, self.piece_index)

    @staticmethod
    def decode(message):
        message_length, message_id, piece_index = unpack('!IBI', message)
        return PeersPieces(piece_index)
