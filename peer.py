import struct

import bitstring
import socket
import logging
import Message
import asyncio
from pubsub import pub
from struct import unpack


class Peer:
    def __init__(self, ip, number_of_pieces,  port=6881):
        self.ip = ip
        self.port = port
        self.number_of_pieces = number_of_pieces
        bitfield_length = number_of_pieces if number_of_pieces % 8 == 0 else number_of_pieces + 8 - number_of_pieces % 8
        self.bitfield = bitstring.BitArray(bitfield_length)
        self.handshake = False
        self.is_active = False
        self.reader = None
        self.writer = None
        self.buffer = b''

        self._peer_interested = False
        self._peer_choked = True
        self._interested = False
        self._choked = True

    @staticmethod
    def analyze_message(message):
        try:
            message_length, message_id = unpack('!IB', message[:5])
            logging.info(f"Message id - {message_id}")
        except struct.error:
            logging.error('Некорректное сообщение, распаковка невозможна')
            return None

        messages_by_id = {0: Message.ChokedMessage, 1: Message.UnChokedMessage,
                          2: Message.InterestedMessage, 3: Message.NotInterestedMessage,
                          4: Message.HaveMessage, 5: Message.PeerSegmentsMessage,
                          6: Message.RequestsMessage, 7: Message.SendPieceMessage,
                          8: Message.CancelMessage}

        if message_id not in messages_by_id:
            logging.error(f'Некорректное сообщение, указан несуществующий id_message: {message_id}')
            return None
        else:
            return messages_by_id[message_id].decode(message)

    async def connect(self) -> bool:
        try:
            self.reader, self.writer = await asyncio.open_connection(self.ip, self.port)
            self.is_active = True
        except (asyncio.TimeoutError, OSError):
            logging.error(f'Socket error: Пир {self.ip}:{self.port} не может быть подключён')
            return False
        return True

    async def send_message_to_peer(self, message: bytes) -> None:
        try:
            self.writer.write(message)
            await self.writer.drain()
        except OSError:
            self.is_active = False
            logging.error(f'Socket error. Невозможно отправить сообщение {message}')

    # region Properties
    @property
    def interested(self) -> bool:
        return self._interested

    @interested.setter
    def interested(self, value: bool) -> None:
        self._interested = value

    @property
    def choked(self) -> bool:
        return self._choked

    @choked.setter
    def choked(self, value: bool) -> None:
        self._choked = value

    @property
    def peer_interested(self) -> bool:
        return self._peer_interested

    @peer_interested.setter
    def peer_interested(self, value: bool) -> None:
        self._peer_interested = value
        if value and self.choked:
            logging.info('Send intereted message!')
            asyncio.create_task(self.send_message_to_peer(Message.UnChokedMessage().encode()))

    @property
    def peer_choked(self) -> bool:
        return self._peer_choked

    @peer_choked.setter
    def peer_choked(self, value: bool) -> None:
        self._peer_choked = value
    # endregion

    def check_for_piece(self, index: int) -> bool:
        return self.bitfield[index]

    async def handle_got_piece(self, piece, peer=None) -> None:
        self.bitfield[piece.piece_index] = True
        # pub.sendMessage('updatePartBitfield', peer=peer, piece_index=piece.piece_index)
        if self.peer_choked and not self.interested:
            await self.send_message_to_peer(Message.InterestedMessage().encode())
            self.interested = True

    async def handle_available_piece(self, message, peer=None) -> None:
        logging.info(f"Bitfield - {len(self.bitfield)}, value: {self.bitfield[:100]}")
        logging.info(f"Message.segments - {len(message.segments)}")

        self.bitfield |= message.segments
        # pub.sendMessage('updateAllBitfield', peer=peer)
        if self.peer_choked and not self.interested:
            await self.send_message_to_peer(Message.InterestedMessage().encode())
            self.interested = True

    # Метод на получение куска
    def handle_send_piece(self, piece_message) -> None:
        # Переделать когда появится piece на отправку с piece=(index, byte_offset, data)
        pub.sendMessage('sendPiece', piece=piece_message)

    # Метод на отправку куска
    def handle_request(self, request) -> None:
        pass
        # if not self.peer_choked and self.peer_interested:
            # pub.sendMessage('requestPiece', request=request, peer=self)

    def handle_handshake(self) -> bool:
        if len(self.buffer) >= 68 and unpack('!B', self.buffer[:1])[0] == 19:
            handshake_message = Message.HandshakeMessage.decode(self.buffer[:68])
            self.handshake = True
            self.buffer = self.buffer[68:]
            return True
        return False

    def handle_continue_connection(self) -> bool:
        if len(self.buffer) >= 4 and unpack('!I', self.buffer[0:4])[0] == 0:
            continue_connection_message = Message.ContinueConnectionMessage.decode(self.buffer[:4])
            self.buffer = self.buffer[4:]
            return True
        return False

    async def close(self):
        self.is_active = False
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
        if self.reader:
            self.reader = None
