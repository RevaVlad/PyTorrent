import logging
import errno
import socket
import asyncio
import Message
from pubsub import pub
import peer as peer_class
from block import Block
from math import ceil
from struct import unpack


class PeerManager:

    def __init__(self, torrent_data):
        self.torrent_data = torrent_data
        self._working_segment = -1

        self.available_pieces = [[0, []] for _ in range(self.torrent_data.total_segments)]
        self.downloaded_blocks = []
        self.pending_blocks = []
        self.missing_blocks = asyncio.Queue()

        # pub.subscribe(self.request_piece, 'requestAllPiece')
        # pub.subscribe(self.peers_bitfield_update_all, 'updateAllBitfield')
        # pub.subscribe(self.peers_bitfield_update_piece, 'updatePartBitfield')

    async def download_segment(self, segment_id):
        if self._working_segment == -1:
            return False
        self._working_segment = segment_id

        segment_length = self.torrent_data.segment_length if segment_id != self.torrent_data.total_segments - 1 \
            else self.torrent_data.total_length % self.torrent_data.segment_length

        total_blocks = ceil(segment_length / Block.BLOCK_LENGTH)
        for block_offset in range(0, (total_blocks - 1) * Block.BLOCK_LENGTH, Block.BLOCK_LENGTH):
            self.missing_blocks.put_nowait(Block(segment_id, block_offset))
        self.missing_blocks.put_nowait(Block(segment_id, segment_length % Block.BLOCK_LENGTH))

        while len(self.downloaded_blocks) < total_blocks:
            pass

    def on_get_block(self, block):
        self.pending_blocks.remove(block)
        self.downloaded_blocks.append(block)

    async def upload_segment(self):
        pass

    def request_piece(self, request=None, peer=None):
        if request is None:
            logging.error('Тело запроса пусто')
        elif peer is None:
            logging.error('Не указан пир, запросивший сегмент')
        else:
            piece_index, byte_offset, block_length = request.index, request.byte_offset, request.block_length
            block = b'need to update'
            peer.send_message_to_peer(Message.SendPieceMessage(piece_index, byte_offset, block).encode())
            # нужно обновить !!!
            # block = получить блок по данным запроса
            # if block:\
            #   peer.send_message_to_peer(Message.SendPieceMessage(piece_index, byte_offset, block).encode())

    def peers_bitfield_update_all(self, peer=None):
        if peer is None:
            logging.error('Не указан пир, у которого необходимо проверить наличие сегментов')
        else:
            for i in range(0, self.torrent_data.total_segments):
                if peer.bitfield[i] == 1 and (self.available_pieces[i][0] == 0 or peer not in self.available_pieces[i][1]):
                    self.available_pieces[i][1].append(peer)
                    self.available_pieces[i][0] += 1

    def peers_bitfield_update_piece(self, peer=None, piece_index=None):
        if peer is None:
            logging.error('Не указан пир, у которого есть сегмент')
        elif piece_index is None:
            logging.error('Не указан индекс для отметки в bitField')
        else:
            if peer not in self.available_pieces[piece_index][1]:
                self.available_pieces[piece_index][1].append(peer)
                self.available_pieces[piece_index][0] = len(self.available_pieces[piece_index][1])

    async def peer_handshake(self, peer=None):
        if peer is None:
            logging.error('Не указан пир, которому нужно отправить handshake')
            return False
        else:
            handshake = Message.HandshakeMessage(self.torrent_data.info_hash)
            await peer.send_message_to_peer(handshake.encode())
            if peer.is_active is False:
                logging.error('Произошла ошибка при handshake-e, проверьте лог')
                return False
            return True

    @staticmethod
    async def read_socket(peer: peer_class):
        try:
            data = await peer.reader.read(4096)
            peer.buffer += data
        except (asyncio.TimeoutError, OSError):
            logging.error('Таймаут чтения с сокета')

    @staticmethod
    async def run(peer: peer_class):
        while peer.is_active:
            await PeerManager.read_socket(peer)

            while len(peer.buffer) > 4 and peer.is_active:
                if (not peer.handshake and peer.handle_handshake()) or peer.handle_continue_connection():
                    continue

                message_length, = unpack("!I", peer.buffer[:4])
                total_length = message_length + 4

                if len(peer.buffer) < total_length:
                    break
                else:
                    message = peer.buffer[:total_length]
                    peer.buffer = peer.buffer[total_length:]

                received_message = peer.analyze_message(message)
                if received_message:
                    await PeerManager.get_new_message(received_message, peer)

    @staticmethod
    async def get_new_message(new_message: Message.Message, peer: peer_class, peer_sent=None):
        match new_message:
            case Message.HandshakeMessage():
                logging.error(f'Обработка Handshake сообщения производится отедльно')
            case Message.ContinueConnectionMessage():
                logging.error(f'Обработка ContinueConnection сообщения производится отедльно')
            case Message.ChokedMessage():
                peer.peer_choked = True
            case Message.UnChokedMessage():
                logging.info('unchocked')
                peer.peer_choked = False
            case Message.InterestedMessage():
                logging.info('interested')
                peer.peer_interested = True
            case Message.NotInterestedMessage():
                logging.info('not interested')
                peer.peer_interested = False
            case Message.HaveMessage():
                logging.info('have massage')
                await peer.handle_got_piece(new_message)
            case Message.PeerSegmentsMessage():
                logging.info('peer segments message')
                await peer.handle_available_piece(new_message)
            case Message.RequestsMessage():
                logging.info('request message')
                await peer.handle_request(new_message)
            case Message.SendPieceMessage():
                logging.info('send piece message')
                await peer.handle_send_piece(new_message)
            case Message.CancelMessage():
                logging.info('CancelMessage')
            case _:
                logging.error(f'Такого типа сообщения нет: {type(new_message)}')
