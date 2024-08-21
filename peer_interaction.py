import asyncio
import logging
import heapq
from segment_downloader import SegmentDownloader
from pubsub import pub


class PeerInteraction:
    MAX_PEER_COUNT = 50

    def __init__(self, torrent):
        self.peers = []
        self.active_peers = 0
        self.available_segments = [(0, [], False) for _ in range(torrent.total_segments)]
        self.segment_heap = [(0, i) for i in range(torrent.total_segments)]
        self.torrent = torrent
        self.is_active = True

    async def add_peer(self, peer):
        connect = await peer.connect()
        if connect:
            if await peer.handle_handshake():
                self.peers.append(peer)
                asyncio.create_task(peer.run())
                pub.subscribe(self.get_bitfield_from_peer, peer.bitfield_update_event)
        else:
            logging.error('Возникли проблемы с установлением соединения с пиром')

    async def add_peers(self, peers):
        for peer in peers:
            await self.add_peer(peer)

    def get_bitfield_from_peer(self, peer):
        for i in range(len(self.available_segments)):
            if peer.bitfield[i] == 1:
                self.available_segments[i][0] += 1
                self.available_segments[i][1].append(peer)
                heapq.heappush(self.segment_heap, (self.available_segments[i][0], i))
        self.active_peers += 1

    def get_most_rare_segment(self):
        count, rarest_index = heapq.heappop(self.segment_heap)
        if self.available_segments[rarest_index][2] is False:
            # Добавить file_writer и torrent_statistics
            return SegmentDownloader(segment_id=rarest_index, torrent_data=self.torrent,
                                     peers=self.available_segments[rarest_index][1][0] if count == 1 else
                                     self.available_segments[rarest_index][1][:2])
        else:
            self.get_most_rare_segment()

    async def block_peer(self, peer):
        if peer in self.peers:
            self.peers.remove(peer)

            self.remove_peer_from_available_segments(peer)

            await peer.close()

    def remove_peer_from_available_segments(self, peer):
        flag = False
        for i in range(len(self.available_segments)):
            if peer in self.available_segments[i][1]:
                flag = True
                self.available_segments[i][0] -= 1
                self.available_segments[i][1].remove(peer)
        if flag:
            self.active_peers -= 1

    def unchoked_peers(self):
        for peer in self.peers:
            if peer.peer_choked is False:
                return True
        return False
