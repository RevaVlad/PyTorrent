import logging
import asyncio
import Message
import parser
from pubsub import pub
from peerconnection import PeerConnection


class SegmentDownloader:
    def __init__(self, segment_id, torrent_data: parser.TorrentData, file_writer, torrent_statistics, peers: list[PeerConnection]):
        self.torrent_data = torrent_data
        self.file_writer = file_writer
        self.torrent_stat = torrent_statistics
        self.peers = peers

        self.segment_id = segment_id

        self.downloaded_blocks = []
        self.pending_blocks = []
        self.missing_blocks = []

        self.sleeping_peers = peers
        self.working_peers = []

        pub.subscribe(self.on_request_piece, peers[0].request_event)
        pub.subscribe(self.on_receive_block, peers[1].receive_event)

    def on_request_piece(self, request=None, peer=None):
        if request is None:
            logging.error('Тело запроса пусто')
        elif peer is None:
            logging.error('Не указан пир, запросивший сегмент')
        else:
            piece_index, byte_offset, block_length = request.index, request.byte_offset, request.block_length
            loop = asyncio.get_event_loop()
            block = loop.run_until_complete(self.file_writer.read(piece_index))[byte_offset: byte_offset + block_length]
            peer.send_message_to_peer(Message.SendPieceMessage(piece_index, byte_offset, block).encode())
            self.torrent_stat.update_uploaded(block_length)

    def on_receive_block(self, message: Message.SendPieceMessage = None):
        if not message:
            logging.error('Сообщение пусто')
        print(self)

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
