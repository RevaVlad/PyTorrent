import socket
from abc import ABC, abstractmethod
from struct import pack, unpack
from random import randint
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


class UDPConnectionMessage:
    """
    <connection_id><action><transaction_id> - input
    <action><transaction_id><connection_id> - output
    """

    def __init__(self):
        self.connection_id = 0x41727101980
        self.action = 0
        self.transaction_id = randint(0, 10 ** 5)

    def encode(self):
        return pack('!Q', self.connection_id) + pack('!I', self.action) + pack('!I', self.transaction_id)

    def decode(self, message):
        self.action, self.transaction_id, self.connection_id = unpack('!IIQ', message)


class UPDTrackerAnnounceInput:
    """
    events: none - 0
    completed - 1
    started - 2
    stopped - 3
    """
    def __init__(self, info_hash, peer_id, connection_id, event=0):
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.connection_id = connection_id
        self.event = event
        self.transaction_id = randint(0, 10 ** 5)

    def encode(self):
        conn_id = pack('!Q', self.connection_id)
        downloaded = pack('!Q', 0)
        left = pack('!Q', 0)
        uploaded = pack('!Q', 0)

        action = pack('!I', 1)
        trans_id = pack('!I', self.transaction_id)
        event = pack('!I', self.event)
        ip = pack('!I', 0)
        key = pack('!I', 0)
        num_want = pack('!i', -1)
        port = pack('!h', 8000)

        return (conn_id + action + trans_id + self.info_hash + self.peer_id + downloaded +
                left + uploaded + event + ip + key + num_want + port)


class UPDTrackerAnnounceOutput:
    def __init__(self):
        self.action = None
        self.transaction_id = None
        self.interval = None
        self.leechers = None
        self.seeders = None
        self.list_peers = []

    def decode(self, message):
        self.action, = unpack('!I', message[:4])
        self.transaction_id, = unpack('!I', message[4:8])
        self.interval, = unpack('!I', message[8:12])
        self.leechers, = unpack('!I', message[12:16])
        self.seeders, = unpack('!I', message[16:20])
        self.list_peers = self._parse_adresses(message[20:])

    def _parse_adresses(self, raw_bytes):
        socks_addr = []
        for i in range(int(len(raw_bytes) / 6)):
            start = i * 6
            end = start + 6
            ip = socket.inet_ntoa(raw_bytes[start:(end - 2)])
            raw_port = raw_bytes[(end - 2):end]
            port = unpack('!H', raw_port)[0]
            socks_addr.append((ip, port))

        return socks_addr


class HandshakeMessage(Message):
    """
    <19><BitTorrent protocol><0x0000000000000000><info_hash><peer_id>
    """

    def __init__(self, info_hash: bytes, peer_id=None):
        self.info_hash = info_hash
        self.peer_id = peer_id if peer_id is not None else b'\x00' * 20

    def encode(self):
        return pack(f'!B19s8s20s20s', 19, b'BitTorrent protocol', b'\x00' * 8, self.info_hash, self.peer_id)

    @staticmethod
    def decode(message):
        identifier_length, identifier, reserved, info_hash, peer_id = unpack('!B19s8s20s20s', message)
        return HandshakeMessage(info_hash, peer_id)


class InterestedMessage(Message):
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
        else:
            return InterestedMessage()


class UnChokedMessage(Message):
    """
    <0001><1>
    """

    def encode(self):
        return pack('!IB', 1, 1)

    @staticmethod
    def decode(message):
        data_length, message_id = unpack('!IB', message)
        if message_id != 1:
            logging.error(f'При запросе на снятие заглушки был получен некорректный индентификатор: {message_id}')
        else:
            return UnChokedMessage()


class PeerSegmentsMessage(Message):
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
        segments, = unpack(f'!{message_length - 1}s', message[5:5 + message_length - 1])
        return PeerSegmentsMessage(bitstring.BitArray(bytes=bytes(segments)))


class RequestsMessage(Message):
    """
    <0013><6><index><byte_offset><block_len>
    """

    def __init__(self, index: int, byte_offset: int, block_len: int):
        self.index = index
        self.byte_offset = byte_offset
        self.block_len = block_len

    def encode(self):
        return pack('!IBIII', 13, 6, self.index, self.byte_offset, self.block_len)

    @staticmethod
    def decode(message):
        message_length, message_id, index, byte_offset, block_len = unpack('!IBIII', message)
        return RequestsMessage(index, byte_offset, block_len)


class SendPieceMessage(Message):
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
        return SendPieceMessage(index, byte_offset, data)


class HaveMessage(Message):
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
        return HaveMessage(piece_index)


class CancelMessage(Message):
    """
    <0013><8><index><byte_offset><block_len>
    """

    def __init__(self, piece_index: int, byte_offset: int, block_len: int):
        self.piece_index = piece_index
        self.byte_offset = byte_offset
        self.block_len = block_len

    def encode(self):
        return pack('!IBIII', 13, 8, self.piece_index, self.byte_offset, self.block_len)

    @staticmethod
    def decode(message):
        message_length, message_id, piece_index, byte_offset, block_len = unpack('!IBIII', message)
        return CancelMessage(piece_index, byte_offset, block_len)


class ContinueConnectionMessage(Message):
    """
    <0000>
    """

    def encode(self):
        return pack('!I', 0)

    @staticmethod
    def decode(message):
        message_length = unpack('!I', message)[0]
        if message_length != 0:
            logging.error('При попытке поддержания соединения было получено неккоректное сообщение: длина не нулевая')
        else:
            return ContinueConnectionMessage()


class ChokedMessage(Message):
    """
    <0001><0>
    """

    def encode(self):
        return pack('!IB', 1, 0)

    @staticmethod
    def decode(message):
        message_length, message_id = unpack('!IB', message)
        if message_id != 0:
            logging.error(f'При запросе на включение заглушки был получен некорректный индентификатор: {message_id}')
        else:
            return ChokedMessage()


class NotInterestedMessage(Message):
    """
    <0001><3>
    """

    def encode(self):
        return pack('!IB', 1, 3)

    @staticmethod
    def decode(message):
        message_length, message_id = unpack('!IB', message)
        if message_id != 3:
            logging.error(f'При запросе на отсутсвие интереса был получен некорректный индентификатор: {message_id}')
        else:
            return NotInterestedMessage()
