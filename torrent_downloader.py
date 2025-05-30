import asyncio
import logging
import configuration
import Message
from segment_downloader import SegmentDownloader, SegmentDownloadStatus, Segment
from peer_connection import PeerConnection
from pubsub import pub
from priority_queue import PriorityQueue
from requests_receiver import PeerReceiver


class Downloader:

    def __init__(self, torrent, file_writer, torrent_statistics, peer_queue: asyncio.Queue):
        self.torrent = torrent
        self.file_writer = file_writer
        self.torrent_statistics = torrent_statistics
        self.peer_queue = peer_queue

        self.active_peers = []
        self.peer_update_tasks = []

        self._peer_connection_task = None

        self.available_segments = [Segment(i) for i in range(torrent.total_segments)]
        self.available_segments_lock = asyncio.Lock()

        self._segment_heap = PriorityQueue()
        self._segment_downloaders = []

        self.bitfield_active = False

    async def download_torrent(self, seed=True):
        await self.get_downloaded_segments()
        self._peer_connection_task = asyncio.create_task(self.peer_connection_task())

        while any(segment.status != SegmentDownloadStatus.SUCCESS for segment in self.available_segments):
            await asyncio.sleep(.1)

            if len(self._segment_downloaders) < configuration.MAX_SEGMENTS_DOWNLOADING_SIMULTANEOUSLY:
                segment_id, finding_result = await self.try_find_rarest_segment()
                if not finding_result:
                    continue

                peers_with_segment = self.available_segments[segment_id].peers
                peers = peers_with_segment[:configuration.MAX_PEER_PEERS_PER_SEGMENT]

                for peer in peers:
                    await self.remove_peer_from_available_segments(peer)

                self.available_segments[segment_id].status = SegmentDownloadStatus.PENDING
                self._segment_downloaders.append(self.start_segment_download(self.available_segments[segment_id],
                                                                             peers))

            await asyncio.sleep(.1)

        if seed:
            while True:
                await asyncio.sleep(1000)

    async def get_downloaded_segments(self):
        for i in range(self.torrent.total_segments):
            if await self.file_writer.check_segment_download(i):
                segment_length = self.torrent.segment_length if i != self.torrent.total_segments - 1 \
                    else self.torrent.total_length % self.torrent.segment_length
                self.torrent_statistics.update_downloaded(segment_length)

                self.available_segments[i].status = SegmentDownloadStatus.SUCCESS
                self.torrent_statistics.update_bitfield(i, True)
        logging.info(self.torrent_statistics.bitfield.bin)

    async def try_find_rarest_segment(self) -> (int, bool):
        if not self._segment_heap:
            return None, False

        count, rarest_index = self._segment_heap.pop()
        segment = self.available_segments[rarest_index]
        if (segment.status == SegmentDownloadStatus.NOT_STARTED
                and segment.peers_count > 0):
            logging.info(f"Found not yet downloaded segment! Next segment is: {rarest_index}")
            return rarest_index, True
        else:
            self._segment_heap.push(count, rarest_index)
            return None, False

    def start_segment_download(self, segment, peers) -> SegmentDownloader:
        downloader = SegmentDownloader(segment, torrent_data=self.torrent,
                                       file_writer=self.file_writer,
                                       torrent_statistics=self.torrent_statistics,
                                       peers=peers)

        pub.subscribe(self.replace_peer, downloader.peer_deletion_event)
        pub.subscribe(self.on_download_end, downloader.downloading_stopped_event)

        downloader.download_segment()
        return downloader

    def on_download_end(self, downloader):
        segment = downloader.segment
        logging.info(f"Segment {segment.id} download was canceled...")
        if segment.status == SegmentDownloadStatus.SUCCESS:
            logging.info("Because it downloaded correctly!!!")
            self.torrent_statistics.update_bitfield(segment.segment_id, True)
            self.send_have_message_to_peers(segment.segment_id)
        elif segment.status == SegmentDownloadStatus.FAILED:
            logging.error("Because it failed :(")
            segment.status = SegmentDownloadStatus.NOT_STARTED
            self._segment_heap.push(self.available_segments[segment.id].peers_count, segment.id)

        if downloader in self._segment_downloaders:
            self._segment_downloaders.remove(downloader)
            logging.info(f"Removing downloader: {downloader}")
        for peer in downloader.peers:
            self.get_bitfield_from_peer(peer)

    def send_have_message_to_peers(self, index):
        asyncio.create_task(self._send_have_message_to_peers_task(index))

    async def _send_have_message_to_peers_task(self, index):
        message = Message.HaveMessage(index)
        for peer in self.active_peers:
            await peer.send_message_to_peer(message)

    async def peer_connection_task(self):
        logging.info("Started peer connection task")
        while True:
            if len(self.active_peers) < configuration.MAX_PEER_COUNT:
                result = True
                while result:
                    result = await self._add_peer_from_queue()
            await asyncio.sleep(.01)

    async def _add_peer_from_queue(self):
        peer = await self.peer_queue.get()
        await self.add_peer(peer)

    async def add_peer(self, peer):
        connect = await peer.connect()
        if connect:
            if await peer.handle_handshake():
                logging.info(f"Connected new peer: ({peer.ip}, {peer.port})")
                self.active_peers.append(peer)
                self.peer_update_tasks.append(asyncio.create_task(peer.run()))
                pub.subscribe(self.get_have_message_from_peer, peer.have_message_event)
                pub.subscribe(self.get_bitfield_from_peer, peer.bitfield_update_event)
                pub.subscribe(self.on_request_piece, peer.request_event)
                self.send_bitfield_to_peer(peer)
                if not isinstance(peer, PeerReceiver):
                    self.check_for_unchoked(peer)
                return True
        logging.error('Возникли проблемы с установлением соединения с пиром')
        return False

    def send_bitfield_to_peer(self, peer):
        asyncio.create_task(self._send_bitfield_to_peer_task(peer))

    async def _send_bitfield_to_peer_task(self, peer:  PeerConnection):
        message = Message.PeerSegmentsMessage(self.torrent_statistics.bitfield)
        await peer.send_message_to_peer(message)

    def on_request_piece(self, request=None, peer=None):
        if request is None:
            logging.error('Тело запроса пусто')
        elif peer is None:
            logging.error('Не указан пир, запросивший сегмент')
        else:
            asyncio.create_task(self._on_request_piece(request, peer))

    async def _on_request_piece(self, request, peer):
        piece_index, byte_offset, block_length = request.index, request.byte_offset, request.block_len
        block = (await self.file_writer.read_segment(piece_index))[byte_offset: byte_offset + block_length]
        await peer.send_message_to_peer(Message.SendPieceMessage(piece_index, byte_offset, block))

    def check_for_unchoked(self, peer):
        _was_unchoked = asyncio.create_task(self._check_for_unchoked_task(peer, 10))

    async def _check_for_unchoked_task(self, peer: PeerConnection, delay):
        await asyncio.sleep(delay)
        if peer.peer_choked is True:
            logging.info(f'Пир {peer.ip} был отключён - не отправил unchoked messagе')
            if peer in self.active_peers:
                self.active_peers.remove(peer)
            await peer.close()
            return False
        return True

    def get_bitfield_from_peer(self, peer):
        asyncio.create_task(self._get_bitfield_from_peer_task(peer))

    async def _get_bitfield_from_peer_task(self, peer):
        for segment in self.available_segments:
            if peer.bitfield[segment.id] == 1:
                segment.add_peer(peer)
                self._segment_heap.push(segment.peers_count, segment.id)
        self.bitfield_active = True

    def get_have_message_from_peer(self, peer, index):
        asyncio.create_task(self._get_have_message_from_peer_task(peer, index))

    async def _get_have_message_from_peer_task(self, peer, index):
        segment = self.available_segments[index]
        segment.add_peer(peer)
        self._segment_heap.push(segment.peers_count, index)
        self.bitfield_active = True

    async def block_peer(self, peer):
        if peer in self.active_peers:
            self.active_peers.remove(peer)
            await self.remove_peer_from_available_segments(peer)
            await peer.close()

    async def remove_peer_from_available_segments(self, peer):
        for segment in self.available_segments:
            if peer in segment.peers:
                segment.remove_peer(peer)
                self._segment_heap.push(segment.peers_count, segment.id)

    def replace_peer(self, segment_downloader: SegmentDownloader):
        other_peers = self.available_segments[segment_downloader.segment.id].peers
        if any(other_peers):
            logging.info(f"Replacing peer for downloader of segment {segment_downloader.segment.id}")
            peer = other_peers.pop(0)
            asyncio.create_task(self.remove_peer_from_available_segments(peer))
            segment_downloader.add_peer(peer)
        else:
            logging.info(
                f"No new peers were provided for segment {segment_downloader.segment.id}, gonna try again later")
            if segment_downloader in self._segment_downloaders:
                self._segment_downloaders.remove(segment_downloader)

    def unchoked_peers(self):
        for peer in self.active_peers:
            if peer.peer_choked is False:
                return True
        return False

    def close(self):
        if self._peer_connection_task:
            self._peer_connection_task.cancel()
        for task in self.peer_update_tasks:
            task.cancel()
        for segment_downloader in self._segment_downloaders:
            segment_downloader.close()
