import struct

import bitstring
import socket
import logging
import Message
from pubsub import pub
from struct import unpack


class Peer:
    def __init__(self, ip, number_of_pieces,  port=6881):
        self.ip = ip
        self.port = port
        self.number_of_peaces = number_of_pieces
        self.bitfield = bitstring.BitArray(number_of_pieces)
        self.handshake = False
        self.is_active = False
        self.socket = None
        self.buffer = b''

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

    def connect(self) -> bool:
        try:
            self.socket = socket.create_connection((self.ip, self.port))
            self.socket.setblocking(False)
            self.is_active = True
        except socket.error:
            logging.error(f'Socket error: Пир {self.ip}:{self.port} не может быть подключён')
            return False
        return True

    def send_message_to_peer(self, message: str) -> None:
        try:
            self.socket.send(message)
        except socket.error:
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
            self.send_message_to_peer(Message.UnChokedMessage().encode())

    @property
    def peer_choked(self) -> bool:
        return self._peer_choked

    @peer_choked.setter
    def peer_choked(self, value: bool) -> None:
        self._peer_choked = value
    # endregion

    def check_for_piece(self, index: int) -> bool:
        return self.bitfield[index]

    def handle_got_piece(self, peer, piece: int) -> None:
        # Нет кода для piece, нужно поставить self.avliable_files[piece.index] = True
        pub.sendMessage('updatePartBitfield', peer, piece)
        if self.peer_choked and not self.interested:
            self.send_message_to_peer(Message.InterestedMessage().encode())
            self.interested = True

    def handle_available_piece(self, available_files, peer) -> None:
        self.bitfield |= available_files
        pub.sendMessage('updateAllBitfield', peer)
        if self.peer_choked and not self.interested:
            self.send_message_to_peer(Message.InterestedMessage().encode())
            self.interested = True

    def handle_send_piece(self, piece_message) -> None:
        pub.sendMessage('sendPiece', piece=(piece_message.index, piece_message.byte_offset, piece_message.data))

    def handle_request(self, request) -> None:
        if not self.peer_choked and self.peer_interested:
            pub.sendMessage('requestPiece', request=request, peer=self)

    def handle_handshake(self) -> bool:
        if len(self.buffer) >= 19 and unpack('!B', self.buffer[:1]) == 19:
            handshake_message = Message.HandshakeMessage.decode(self.buffer)
            self.handshake = True
            self.buffer = self.buffer[68:]
            return True
        return False

    def handle_continue_connection(self) -> bool:
        if len(self.buffer) >= 4 and unpack('!I', self.buffer[0:4]) == 0:
            continue_connection_message = Message.ContinueConnectionMessage.decode(self.buffer)
            return True
        else:
            return False

    def get_message(self):
        while len(self.buffer) > 4 and self.is_active:
            if (not self.handshake and self.handle_handshake()) or self.handle_continue_connection:
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
                yield received_message

    def close(self):
        # self.close_connection()
        pass