import asyncio
import logging
from segment_downloader import SegmentDownloader, DownloadResult
from peer_connection import PeerConnection
from pubsub import pub
from priority_queue import PriorityQueue


class TorrentDownloader:
    MAX_PEER_COUNT = 50
    MAX_SEGMENTS_DOWNLOADING_SIMULTANEOUSLY = 5

    def __init__(self, torrent, file_writer, torrent_statistics, peer_queue: asyncio.Queue):
        self.torrent = torrent
        self.file_writer = file_writer
        self.torrent_statistics = torrent_statistics
        self.peer_queue = peer_queue

        self.active_peers = []
        self.peer_update_tasks = []

        self._peer_connection_task = None

        self.available_segments = [[0, [], False] for _ in range(torrent.total_segments)]
        self.available_segments_lock = asyncio.Lock()

        self._segment_heap = PriorityQueue()
        self._segment_downloaders = []

        # self.segments_strikes = [0] * torrent.total_segments
        self.bitfield_active = False

    async def download_torrent(self):
        self._peer_connection_task = asyncio.create_task(self.peer_connection_task())
        while any(x[2] is False for x in self.available_segments):
            logging.info(f'Current peers: {len(self.active_peers)}')
            if len(self._segment_downloaders) < TorrentDownloader.MAX_SEGMENTS_DOWNLOADING_SIMULTANEOUSLY:
                segment_id = await self.find_rarest_segment()
                peers_info = self.available_segments[segment_id]
                peers = peers_info[1][:self.MAX_PEER_COUNT]

                for peer in peers:
                    await self.remove_peer_from_available_segments(peer)

                self._segment_downloaders.append(self.start_segment_download(segment_id, peers))

            await asyncio.sleep(.1)

    async def find_rarest_segment(self) -> int:
        logging.info("Searching for next rarest segment")
        while True:
            if not self._segment_heap:
                await asyncio.sleep(0.1)
                continue

            count, rarest_index = self._segment_heap.pop()
            if self.available_segments[rarest_index][2] is False and self.available_segments[rarest_index][0] != 0:
                logging.info(f"The next segment in queue: {rarest_index}")
                return rarest_index
            else:
                self._segment_heap.push(count, rarest_index)
                await asyncio.sleep(0.1)

    def start_segment_download(self, segment_id, peers) -> SegmentDownloader:
        downloader = SegmentDownloader(segment_id=segment_id, torrent_data=self.torrent,
                                       file_writer=self.file_writer,
                                       torrent_statistics=self.torrent_statistics,
                                       peers=peers)

        pub.subscribe(self.replace_peer, downloader.peer_deletion_event)
        pub.subscribe(self.on_download_end, downloader.downloading_stopped_event)

        downloader.download_segment()
        return downloader

    def on_download_end(self, downloader):
        if downloader in self._segment_downloaders:
            self._segment_downloaders.remove(downloader)
        logging.info(f"Segment {downloader.segment_id} download was canceled...")
        for peer in downloader.peers_strikes:
            self.get_bitfield_from_peer(peer)
        if downloader.download_result == DownloadResult.COMPLETED:
            logging.info("Because it downloaded correctly!!!")
            self.available_segments[downloader.segment_id][2] = True
        elif downloader.download_result == DownloadResult.FAILED:
            logging.error("Because it failed :(")
            self._segment_heap.push(self.available_segments[downloader.segment_id][0], downloader.segment_id)

    async def peer_connection_task(self):
        logging.info("Started peer connection task")
        while True:
            if len(self.active_peers) < TorrentDownloader.MAX_PEER_COUNT:
                result = True
                while result:
                    result = await self._add_peer()
            await asyncio.sleep(.01)

    async def _add_peer(self):
        (peer_ip, peer_port) = await self.peer_queue.get()
        peer = PeerConnection(peer_ip, self.torrent.total_segments, self.torrent.info_hash, peer_port)
        connect = await peer.connect()
        if connect:
            if await peer.handle_handshake():
                logging.info(f"Connected new peer: ({peer_ip}, {peer_port})")
                self.active_peers.append(peer)
                self.peer_update_tasks.append(asyncio.create_task(peer.run()))
                pub.subscribe(self.get_have_message_from_peer, peer.have_message_event)
                pub.subscribe(self.get_bitfield_from_peer, peer.bitfield_update_event)
                self.check_for_unchoked(peer)
                return True

        logging.error('Возникли проблемы с установлением соединения с пиром')
        return False

    def check_for_unchoked(self, peer):
        _was_unchoked = asyncio.create_task(self._check_for_unchoked(peer, 10))

    async def _check_for_unchoked(self, peer: PeerConnection, delay):
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
        async with self.available_segments_lock:
            for i in range(len(self.available_segments)):
                if peer.bitfield[i] == 1:
                    self.available_segments[i][0] += 1
                    self.available_segments[i][1].append(peer)
                    self._segment_heap.push(self.available_segments[i][0], i)
            self.bitfield_active = True

    def get_have_message_from_peer(self, peer, index):
        asyncio.create_task(self._get_have_message_from_peer_task(peer, index))

    async def _get_have_message_from_peer_task(self, peer, index):
        async with self.available_segments_lock:
            self.available_segments[index][0] += 1
            self.available_segments[index][1].append(peer)
            self._segment_heap.push(self.available_segments[index][0], index)
        self.bitfield_active = True

    async def block_peer(self, peer):
        if peer in self.active_peers:
            await self.remove_peer_from_available_segments(peer)
            await peer.close()
            self.active_peers.remove(peer)

    async def remove_peer_from_available_segments(self, peer):
        for i in range(len(self.available_segments)):
            if peer in self.available_segments[i][1]:
                async with self.available_segments_lock:
                    self.available_segments[i][0] -= 1
                    self.available_segments[i][1].remove(peer)
                    self._segment_heap.push(self.available_segments[i][0], i)

    def replace_peer(self, segment_downloader: SegmentDownloader):
        other_peers = self.available_segments[segment_downloader.segment_id][1]
        if any(other_peers):
            logging.info(f"Replacing peer for downloader of segment {segment_downloader.segment_id}")
            peer = other_peers.pop(0)
            asyncio.create_task(self.remove_peer_from_available_segments(peer))
            segment_downloader.add_peer(peer)
        else:
            logging.info(
                f"No new peers were provided for segment {segment_downloader.segment_id}, gonna try again later")
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
