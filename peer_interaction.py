import asyncio
import logging
import heapq
from segment_downloader import SegmentDownloader
from peer_connection import PeerConnection
from pubsub import pub


class TorrentDownloader:
    MAX_PEER_COUNT = 50
    MAX_SEGMENTS_DOWNLOADING_SIMULTANEOUSLY = 1

    def __init__(self, torrent, file_writer, torrent_statistics, peer_queue: asyncio.Queue):
        self.torrent = torrent
        self.file_writer = file_writer
        self.torrent_statistics = torrent_statistics
        self.peer_queue = peer_queue

        self.active_peers = []
        self.peer_update_tasks = []
        self._peer_connection_task = None

        self.available_segments = [(0, [], False) for _ in range(torrent.total_segments)]
        self.available_segments_lock = asyncio.Lock()

        self.segment_heap = [(0, i) for i in range(torrent.total_segments)]
        self.segment_download_tasks = []
        # self.segments_strikes = [0] * torrent.total_segments
        self.is_active = True

    async def download_torrent(self):
        self._peer_connection_task = asyncio.create_task(self.peer_connection_task())
        while len(self.segment_heap) or len(self.segment_download_tasks):
            if len(self.segment_download_tasks) < TorrentDownloader.MAX_SEGMENTS_DOWNLOADING_SIMULTANEOUSLY:
                self.segment_download_tasks.append(asyncio.create_task(self.download_rarest_segment()))

            for task in self.segment_download_tasks:
                try:
                    result = task.result()
                    if not result:
                        # TODO: Добавить наказание для пиров, если сегмент не удалось скачать несколько раз подряд
                        #  (возможно для начала стоит убавлять кол-во пиров, и если один пир не может скачать, то блокнуть его)
                        pass
                except (asyncio.CancelledError, asyncio.InvalidStateError):
                    pass

            await asyncio.sleep(5)

    async def peer_connection_task(self):
        while True:
            if len(self.active_peers) < TorrentDownloader.MAX_PEER_COUNT:
                result = True
                while result:
                    result = await self.add_peer()
            await asyncio.sleep(1)

    async def try_get_new_peer(self) -> (str, int, bool):
        if len(self.active_peers) >= TorrentDownloader.MAX_PEER_COUNT:
            logging.error("Уже достигнуто максимальное кол-во пиров")
            return None, None, False
        peer_task = asyncio.create_task(self.peer_queue.get())
        await asyncio.sleep(1)
        try:
            (peer_ip, peer_port) = peer_task.result()
            logging.info(f"В очереди новый пир: ({peer_ip}, {peer_port})")
            return peer_ip, peer_port, True
        except (asyncio.InvalidStateError, asyncio.CancelledError):
            logging.error("В очереди нету пиров")
            return None, None, False

    async def add_peer(self):
        (peer_ip, peer_port, operation_result) = await self.try_get_new_peer()
        if not operation_result:
            return False
        peer = PeerConnection(peer_ip, self.torrent.total_segments, self.torrent.info_hash, peer_port)
        connect = await peer.connect()
        if connect:
            if await peer.handle_handshake():
                logging.info(f"Connected new peer: ({peer_ip}, {peer_port})")
                self.active_peers.append(peer)
                self.peer_update_tasks.append(asyncio.create_task(peer.run()))
                pub.subscribe(self.get_bitfield_from_peer, peer.bitfield_update_event)
                return True

        logging.error('Возникли проблемы с установлением соединения с пиром')
        return False

    def get_bitfield_from_peer(self, peer):
        asyncio.create_task(self._get_bitfield_from_peer_task(peer))

    async def _get_bitfield_from_peer_task(self, peer):
        async with self.available_segments_lock:
            for i in range(len(self.available_segments)):
                if peer.bitfield[i] == 1:
                    self.available_segments[i][0] += 1
                    self.available_segments[i][1].append(peer)
                    heapq.heappush(self.segment_heap, (self.available_segments[i][0], i))

    async def download_rarest_segment(self):
        while True:
            count, rarest_index = heapq.heappop(self.segment_heap)
            if self.available_segments[rarest_index][2] is False and self.available_segments[rarest_index][0] != 0:
                downloader = SegmentDownloader(segment_id=rarest_index, torrent_data=self.torrent,
                                               file_writer=self.file_writer, torrent_statistics=self.torrent_statistics,
                                               peers=self.available_segments[rarest_index][1][0] if count == 1 else
                                               self.available_segments[rarest_index][1][:2])
                for peer in downloader.peers_strikes:
                    await self.remove_peer_from_available_segments(peer)

                result = await downloader.download_segment()

                # TODO: придумать что делать с блокировкой пиров
                heapq.heappush(self.segment_heap, (count, rarest_index))
                for peer in downloader.peers_strikes:
                    self.active_peers.append(peer)
                if not result:
                    await self.download_rarest_segment()
            else:
                await self.download_rarest_segment()

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
                    self.active_peers.remove(peer)

    def unchoked_peers(self):
        for peer in self.active_peers:
            if peer.peer_choked is False:
                return True
        return False

    def close(self):
        self.is_active = False
        if self._peer_connection_task:
            self._peer_connection_task.cancel()
        for task in self.peer_update_tasks:
            task.cancel()
        for task in self.segment_download_tasks:
            task.cancel()