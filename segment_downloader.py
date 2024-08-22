import logging
import asyncio
import Message
import parser
import math
import hashlib
from pubsub import pub
from peer_connection import PeerConnection
from block import Block


class SegmentDownloader:
    MAX_STRIKES_PER_PEER = 3
    MAX_PENDING_BLOCKS = 10

    PEER_DELETION_EVENT = 'peerDeleted'  # + segment_id, args: segment_downloader

    def __init__(self, segment_id, torrent_data: parser.TorrentData,
                 file_writer, torrent_statistics, peers: list[PeerConnection]):
        self.torrent_data = torrent_data
        self.file_writer = file_writer
        self.torrent_stat = torrent_statistics
        self.peer_deletion_event = SegmentDownloader.PEER_DELETION_EVENT + str(segment_id)
        self.segment_id = segment_id

        segment_length = torrent_data.segment_length if segment_id == torrent_data.total_segments - 1 \
            else torrent_data.total_length % torrent_data.segment_length

        self.blocks_count = math.ceil(segment_length / Block.BLOCK_LENGTH)

        self.downloaded_blocks = set()
        self.missing_blocks = ([Block(self.segment_id, i * Block.BLOCK_LENGTH) for i in range(self.blocks_count - 1)] +
                               [Block(self.segment_id, (self.blocks_count - 1) * Block.BLOCK_LENGTH,
                                      segment_length % Block.BLOCK_LENGTH)])
        logging.info(self.missing_blocks)

        self.tasks = {peer: set() for peer in peers}
        self.peers_strikes = {peer: 0 for peer in peers}

        for peer in peers:
            pub.subscribe(self.on_request_piece, peer.request_event)
            pub.subscribe(self.on_receive_block, peer.receive_event)

    async def download_segment(self):
        logging.info('Starting downloading segment')
        '''
        if all(len(tasks) == 0 for tasks in self.tasks.values()):
            logging.info('Initializing first task')
            lazy_peer = min(list(self.tasks), key=lambda peer: len(self.tasks[peer]))
            block = self.missing_blocks.pop()
            await self.request_block(block, lazy_peer)
        '''

        while len(self.downloaded_blocks) != self.blocks_count:
            self.check_tasks_completion()
            await self.check_peers_connection()

            if any(self.tasks) and any(self.missing_blocks) and sum(len(self.tasks[peer]) for peer in self.tasks) < SegmentDownloader.MAX_PENDING_BLOCKS:
                logging.info('i am in loop')
                lazy_peer = min(list(self.tasks), key=lambda peer: len(self.tasks[peer]))
                block = self.missing_blocks.pop()
                await self.request_block(block, lazy_peer)

            await asyncio.sleep(.1)

        data = self.assemble_segment()
        logging.info(hashlib.sha1(data).digest())
        logging.info(self.torrent_data.segments_hash[self.segment_id])
        if hashlib.sha1(data).digest() != self.torrent_data.segments_hash[self.segment_id]:
            logging.error(f"Не удалось скачать сегмент №{self.segment_id} (хэш сегмента был неверным)")
            return False

        self.torrent_stat.update_downloaded(len(data))
        await self.file_writer.write_segment(self.segment_id, data)

    def check_tasks_completion(self):
        for peer in self.tasks:
            for block in self.tasks[peer].copy():
                if block.status == Block.Missing:
                    logging.info(f'I strike peer: {peer.ip}')
                    self.peers_strikes[peer] += 1
                    self.tasks[peer].remove(block)
                    self.missing_blocks.append(block)
                elif block.status == Block.Retrieved:
                    logging.info(f'I delete but retried {peer.ip}')
                    self.tasks[peer].remove(block)
                    self.downloaded_blocks.add(block)

    async def check_peers_connection(self):
        for peer in list(self.peers_strikes):
            if not peer.is_active or self.peers_strikes[peer] > SegmentDownloader.MAX_STRIKES_PER_PEER:
                del self.peers_strikes[peer]
                del self.tasks[peer]
                await peer.close()
                pub.sendMessage(self.peer_deletion_event, segment_downloader=self)

    async def request_block(self, block, peer):
        logging.info('request block')
        block.status = Block.Pending
        message = Message.RequestsMessage(block.segment_id, block.offset, block.length)
        logging.info(f'{block.offset, block.segment_id}')
        self.tasks[peer].add(block)
        block.change_status_to_missing(delay=10)
        await peer.send_message_to_peer(message.encode())

    def on_request_piece(self, request=None, peer=None):
        if request is None:
            logging.error('Тело запроса пусто')
        elif peer is None:
            logging.error('Не указан пир, запросивший сегмент')
        else:
            piece_index, byte_offset, block_length = request.index, request.byte_offset, request.block_len
            loop = asyncio.get_event_loop()
            block = loop.run_until_complete(self.file_writer.read(piece_index))[byte_offset: byte_offset + block_length]
            peer.send_message_to_peer(Message.SendPieceMessage(piece_index, byte_offset, block).encode())
            self.torrent_stat.update_uploaded(block_length)

    def on_receive_block(self, request=None, peer=None):
        logging.info(f'{request.index}, {request.byte_offset}')
        logging.info('received block')
        if not request:
            logging.error('Сообщение пусто')
            return
        if not peer:
            logging.error('Не указан пир')
            return

        block = Block(request.index, request.byte_offset, len(request.data))
        logging.info(len(self.tasks[peer]))
        if block not in self.tasks[peer]:
            logging.error("Получен блок, который не был запрошен")
            return
        logging.info('update all')
        self.tasks[peer].remove(block)
        block.data = request.data
        self.downloaded_blocks.add(block)

    def assemble_segment(self) -> bytes:
        logging.info([block.offset for block in sorted(self.downloaded_blocks, key=lambda block: block.offset)])
        return b''.join([block.data for block in sorted(self.downloaded_blocks, key=lambda block: block.offset)])

    def add_peer(self, peer):
        self.peers_strikes[peer] = 0
        self.tasks[peer] = set()
