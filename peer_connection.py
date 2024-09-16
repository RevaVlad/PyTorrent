import struct
import time

import bitstring
import socket
import logging
import Message
import asyncio
from pubsub import pub
from struct import unpack


class PeerConnection:
    ID = 0

    REQUEST_PIECE_EVENT = 'requestPiece'  # + ip + id, args: message, peer
    RECEIVE_BLOCK_EVENT = 'sendPiece'  # + ip + id, args: request, peer
    BITFIELD_UPDATE_EVENT = 'bitfieldUpdate'  # + ip + id, args: peer
    HAVE_MESSAGE_EVENT = 'hasMessage'  # + ip + id, args: index, peer

    def __init__(self, ip, number_of_pieces: int, info_hash, port=6881):
        PeerConnection.ID += 1

        self.ip = ip
        self.port = port
        self.number_of_pieces = number_of_pieces
        self.info_hash = info_hash

        self.receive_event = PeerConnection.RECEIVE_BLOCK_EVENT + ip + str(PeerConnection.ID)
        self.request_event = PeerConnection.REQUEST_PIECE_EVENT + ip + str(PeerConnection.ID)
        self.bitfield_update_event = PeerConnection.BITFIELD_UPDATE_EVENT + ip + str(PeerConnection.ID)
        self.have_message_event = PeerConnection.HAVE_MESSAGE_EVENT + ip + str(PeerConnection.ID)

        bitfield_length = number_of_pieces if number_of_pieces % 8 == 0 else number_of_pieces + 8 - number_of_pieces % 8
        self.bitfield = bitstring.BitArray(bitfield_length)

        self.handshake = False
        self.is_active = False
        self.reader = None
        self.writer = None
        self.buffer = b''
        self.socket_lock = asyncio.Lock()

        self._peer_interested = False
        self._peer_choked = True
        self._interested = False
        self._choked = True

    @staticmethod
    def analyze_message(message):
        try:
            message_length, message_id = unpack('!IB', message[:5])
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

    async def send_message_to_peer(self, message: Message.Message) -> bool:
        if isinstance(message, Message.SendPieceMessage):
            logging.info("Sending block")
        if not self.handshake:
            allowed_messages = (
                Message.HandshakeMessage, Message.PeerSegmentsMessage, Message.InterestedMessage)
            if all(not isinstance(message, message_type) for message_type in allowed_messages):
                return False

        # logging.info(message)
        message = message.encode()
        try:
            self.writer.write(message)
            await self.writer.drain()
            return True
        except OSError as e:
            self.is_active = False
            #logging.error(f'Socket error {e.errno} {e.strerror}. Невозможно отправить сообщение {message}')
            return False

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
            asyncio.create_task(self.send_message_to_peer(Message.UnChokedMessage()))

    @property
    def peer_choked(self) -> bool:
        return self._peer_choked

    @peer_choked.setter
    def peer_choked(self, value: bool) -> None:
        self._peer_choked = value

    # endregion

    def check_for_piece(self, index: int) -> bool:
        return self.bitfield[index]

    async def handle_got_piece(self, message) -> None:
        self.bitfield[message.piece_index] = True
        pub.sendMessage(self.have_message_event, index=message.piece_index, peer=self)
        if self.peer_choked and not self.interested:
            await self.send_message_to_peer(Message.InterestedMessage())
            self.interested = True

    async def handle_handshake(self):
        handshake = Message.HandshakeMessage(self.info_hash)
        await self.send_message_to_peer(handshake)
        if self.is_active is False:
            logging.error('Произошла ошибка при handshake-e, пир неактивен')
            return False
        return True

    async def handle_available_piece(self, message) -> None:
        self.bitfield = message.segments
        pub.sendMessage(self.bitfield_update_event, peer=self)
        if self.peer_choked and not self.interested:
            await self.send_message_to_peer(Message.InterestedMessage())
            self.interested = True

    def handle_piece_receive(self, piece_message) -> None:
        pub.sendMessage(self.receive_event, request=piece_message, peer=self)

    def handle_piece_request(self, request) -> None:
        if not self.peer_choked and self.peer_interested:
            pub.sendMessage(self.request_event, request=request, peer=self)

    def handle_handshake_for_buffer(self) -> bool:
        if len(self.buffer) >= 68 and unpack('!B', self.buffer[:1])[0] == 19:
            handshake_message = Message.HandshakeMessage.decode(self.buffer[:68])
            self.handshake = True
            self.buffer = self.buffer[68:]
            return True
        return False

    def handle_continue_connection(self) -> bool:
        if len(self.buffer) >= 4 and unpack('!I', self.buffer[:4])[0] == 0:
            continue_connection_message = Message.ContinueConnectionMessage.decode(self.buffer[:4])
            self.buffer = self.buffer[4:]
            return True
        return False

    async def read_socket(self):
        try:
            data = await self.reader.read(4096)
            self.buffer += data
        except (asyncio.TimeoutError, OSError):
            logging.error('Таймаут чтения с сокета')
            self.is_active = False

    async def run(self):
        self.peer_interested = True

        if not self.interested and self.bitfield.any(True):
            await self.send_message_to_peer(Message.InterestedMessage())
            self.interested = True

        while self.is_active:
            await self.read_socket()
            while len(self.buffer) > 4 and self.is_active:
                if (not self.handshake and self.handle_handshake_for_buffer()) or self.handle_continue_connection():
                    continue

                message_length, = unpack("!I", self.buffer[:4])
                total_length = message_length + 4

                if len(self.buffer) < total_length:
                    break
                else:
                    message = self.buffer[:total_length]
                    self.buffer = self.buffer[total_length:]

                    received_message = self.analyze_message(message)
                    if received_message:
                        await self.handle_message(received_message)
            await asyncio.sleep(0.1)

    async def handle_message(self, new_message):
        match new_message:
            case Message.HandshakeMessage():
                logging.error(f'Обработка Handshake сообщения производится отдельно')
            case Message.ContinueConnectionMessage():
                logging.error(f'Обработка ContinueConnection сообщения производится отдельно')
            case Message.ChokedMessage():
                self.peer_choked = True
            case Message.UnChokedMessage():
                self.peer_choked = False
            case Message.InterestedMessage():
                self.peer_interested = True
            case Message.NotInterestedMessage():
                self.peer_interested = False
            case Message.HaveMessage():
                logging.info('got have message')
                await self.handle_got_piece(new_message)
            case Message.PeerSegmentsMessage():
                logging.info('got peer segments message')
                await self.handle_available_piece(new_message)
            case Message.RequestsMessage():
                self.handle_piece_request(new_message)
            case Message.SendPieceMessage():
                self.handle_piece_receive(new_message)
            case Message.CancelMessage():
                logging.info('got cancel message')
            case _:
                logging.error(f'Такого типа сообщения нет: {type(new_message)}')

    async def close(self):
        self.is_active = False
        if self.writer:
            self.writer.close()
            # await self.writer.wait_closed()
        if self.reader:
            self.reader = None
        self.is_active = False
