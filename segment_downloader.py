import logging
import asyncio
import Message
import parser
import math
import hashlib
import configuration

from enum import Enum
from pubsub import pub
from peer_connection import PeerConnection
from block import Block


class SegmentDownloadStatus(Enum):
    NOT_STARTED = 0
    PENDING = 1
    FAILED = 2
    SUCCESS = 3


class Segment:
    def __init__(self, id):
        self.id = id

        self.is_downloaded = False
        self.peers = []
        self.peers_count = 0
        self._status = SegmentDownloadStatus.NOT_STARTED

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value: SegmentDownloadStatus):
        self._status = value

    def add_peer(self, peer):
        self.peers.append(peer)
        self.peers_count += 1

    def remove_peer(self, peer):
        self.peers.remove(peer)
        self.peers_count -= 1


class SegmentDownloader:

    PEER_DELETION_EVENT = 'peerDeleted'  # + segment.id, args: segment_downloader
    DOWNLOADING_STOPPED_EVENT = 'downloadingStopped'  # + segment.id, args: segment_downloader

    def __init__(self, segment, torrent_data: parser.TorrentData,
                 file_writer, torrent_statistics, peers: list[PeerConnection]):
        self.torrent_data = torrent_data
        self.file_writer = file_writer
        self.torrent_stat = torrent_statistics
        self.segment = segment
        self.download_result = SegmentDownloadStatus.PENDING

        self.peer_deletion_event = SegmentDownloader.PEER_DELETION_EVENT + str(segment.id)
        self.downloading_stopped_event = SegmentDownloader.DOWNLOADING_STOPPED_EVENT + str(segment.id)

        segment_length = torrent_data.segment_length if segment.id != torrent_data.total_segments - 1 \
            else torrent_data.total_length % torrent_data.segment_length

        self.blocks_count = math.ceil(segment_length / Block.BLOCK_LENGTH)

        self.downloaded_blocks = set()
        self.missing_blocks = ([Block(self.segment.id, i * Block.BLOCK_LENGTH) for i in range(self.blocks_count - 1)] +
                               [Block(self.segment.id, (self.blocks_count - 1) * Block.BLOCK_LENGTH,
                                      segment_length % Block.BLOCK_LENGTH)])

        self.tasks = {peer: set() for peer in peers}
        self.peers_strikes = {peer: 0 for peer in peers}
        self.downloading_task = None

        for peer in peers:
            pub.subscribe(self.on_receive_block, peer.receive_event)

    def download_segment(self):
        self.downloading_task = asyncio.create_task(self._download_segment())

    async def _download_segment(self):
        logging.info('Starting downloading segment')

        while len(self.downloaded_blocks) != self.blocks_count:
            self.check_tasks_completion()
            await self.check_peers_connection()

            while (any(self.tasks) and any(self.missing_blocks)
                   and sum(len(self.tasks[peer]) for peer in self.tasks) < configuration.MAX_PENDING_BLOCKS):
                lazy_peer = min(list(self.tasks), key=lambda peer: len(self.tasks[peer]))
                block = self.missing_blocks.pop()
                await self.request_block(block, lazy_peer)

            await asyncio.sleep(.01)

        data = self.assemble_segment()
        if hashlib.sha1(data).digest() != self.torrent_data.segments_hash[self.segment.id]:
            self.segment.status = SegmentDownloadStatus.FAILED
            pub.sendMessage(self.downloading_stopped_event, downloader=self)
            return

        self.torrent_stat.update_downloaded(len(data))
        self.segment.status = SegmentDownloadStatus.SUCCESS
        await self.file_writer.write_segment(self.segment.id, data)
        pub.sendMessage(self.downloading_stopped_event, downloader=self)

    def check_tasks_completion(self):
        for peer in self.tasks:
            for block in self.tasks[peer].copy():
                if block.status == Block.Missing:
                    logging.info(f"Striked peer: {peer.ip}")
                    self.peers_strikes[peer] += 1
                    self.tasks[peer].remove(block)
                    self.missing_blocks.append(block)
                elif block.status == Block.Retrieved:
                    logging.info(f'Deleted {peer.ip}')
                    self.tasks[peer].remove(block)
                    self.downloaded_blocks.add(block)

    async def check_peers_connection(self):
        for peer in list(self.peers_strikes):
            if not peer.is_active or self.peers_strikes[peer] > configuration.MAX_STRIKES_PER_PEER:
                logging.info(f"Peer was too slow, it got soft ban {peer.ip}")
                del self.peers_strikes[peer]
                del self.tasks[peer]
                await peer.close()
                pub.sendMessage(self.peer_deletion_event, segment_downloader=self)

    async def request_block(self, block, peer):
        message = Message.RequestsMessage(block.segment_id, block.offset, block.length)
        if await peer.send_message_to_peer(message):
            block.status = Block.Pending
            self.tasks[peer].add(block)
            block.change_status_to_missing(delay=2)
        else:
            self.missing_blocks.append(block)

    def on_receive_block(self, request=None, peer=None):
        if not request:
            logging.error('Сообщение пусто')
            return
        if not peer:
            logging.error('Не указан пир')
            return

        block = Block(request.index, request.byte_offset, len(request.data))
        if block not in self.tasks[peer]:
            logging.error("Получен блок, который не был запрошен")
            return
        self.tasks[peer].remove(block)
        block.data = request.data
        self.downloaded_blocks.add(block)

    def assemble_segment(self) -> bytes:
        result = b''.join([block.data for block in sorted(self.downloaded_blocks, key=lambda block: block.offset)])
        return result

    def add_peer(self, peer):
        self.peers_strikes[peer] = 0
        self.tasks[peer] = set()

        pub.subscribe(self.on_receive_block, peer.receive_event)

    @property
    def peers(self):
        return list(self.peers_strikes)

    def close(self):
        for peer in self.tasks:
            for block in self.tasks[peer].copy():
                if block.status == Block.Pending:
                    block.close()

        self.downloading_task.cancel()
