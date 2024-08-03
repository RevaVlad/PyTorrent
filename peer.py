import bitstring
import socket
import logging


class Peer:
    def __init__(self, ip, number_of_pieces,  port=6881):
        self.ip = ip
        self.port = port
        self.number_of_peaces = number_of_pieces
        self.available_files = bitstring.BitArray(number_of_pieces)
        self.handshake = False
        self.is_active = False
        self.socket = None

        self._peer_interested = False
        self._peer_choked = True
        self._interested = False
        self._choked = True

    def connect(self) -> bool:
        try:
            self.socket = socket.create_connection((self.ip, self.port))
            self.socket.setblocking(False)
            self.is_active = True
        except socket.error:
            logging.error(f'Socket error: Пир {self.ip}:{self.port} не может быть подключён ')
            return False
        return True

    def send_message_to_peer(self, message: str) -> None:
        try:
            self.socket.send(message)
        except socket.error as error:
            logging.error(f'Socket error: {error}. Невозможно отправить сообщение {message}')

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
            self.send_message_to_peer('Реализовать UNCHOKED Message')

    @property
    def peer_choked(self) -> bool:
        return self._peer_choked

    @peer_choked.setter
    def peer_choked(self, value: bool) -> None:
        self._peer_choked = value
    # endregion

    def check_for_piece(self, index: int) -> bool:
        return self.available_files[index]

    def handle_got_piece(self, piece: int) -> None:
        # Занести в bit_field по индексу piece что у нас теперь есть кусок

        if self.choked and not self.interested:
            # Отправить сообщение об интересе
            self.interested = True

    def handle_available_piece(self, available_files) -> None:
        self.available_files = available_files

        if self.choked and not self.interested:
            # Отправить сообщение об интересе
            self.interested = True

    def handle_piece(self):
        # Разобраться с библиотекой pubsub и паттерном издатель-подписчик
        pass

    def handle_request(self):
        # Аналогично выше
        pass

    def handle_handshake(self):
        # Отправляем сообщение handshake
        self.handshake = True
        # Обновить буфер
        # Обработать возможные исключения(отклонение и подобные)

    def get_message(self):
        pass
        # Сделать после создания всех типов сообщений
