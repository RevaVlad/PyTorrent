import asyncio
import logging
from segment_downloader import SegmentDownloader
from pubsub import pub


class PeerInteraction:
    def __init__(self, torrent):
        self.peers = []
        self.available_segments = [[0, []] for _ in range(torrent.total_segments)]
        self.torrent = torrent
        self.is_active = True

    async def add_peer(self, peers):
        for peer in peers:
            connect = await peer.connect()
            if connect:
                if await peer.handle_handshake():
                    self.peers.append(peer)
                    asyncio.create_task(peer.run())
                    pub.subscribe(self.get_bitfield_from_peer, peer.bitfield_update_event)
            else:
                logging.error('Возникли проблемы с установлением соединения с пиром')

    def get_bitfield_from_peer(self, peer):
        for i in range(len(self.available_segments)):
            if peer.bitfield[i] == 1:
                self.available_segments[i][0] += 1
                self.available_segments[i][1].append(peer)

    def remove_peer(self, peer):
        if peer in self.peers:
            peer.close()
            self.peers.remove(peer)

        for i in range(len(self.available_segments)):
            if peer in self.available_segments[i][1]:
                self.available_segments[i][0] -= 1
                self.available_segments[i][1].remove(peer)

    def unchoked_peers(self):
        for peer in self.peers:
            if peer.peer_choked is False:
                return True
        return False

