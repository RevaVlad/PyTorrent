import asyncio
import logging
from threading import Thread
from segment_downloader import SegmentDownloader


class PeerInteraction(Thread):
    def __init__(self, torrent):
        super().__init__()
        self.peers = []
        self.torrent = torrent
        self.is_active = True
        self.peer_manager = SegmentDownloader(self.torrent)

    async def add_peer(self, peers):
        for peer in peers:
            connect = await peer.connect()
            if connect:
                if await self.peer_manager.peer_handshake(peer):
                    self.peers.append(peer)
                    asyncio.create_task(self.peer_manager.run(peer))
            else:
                logging.error('Возникли проблемы с установлением соединения с пиром')

    def remove_peer(self, peer):
        if peer in self.peers:
            peer.close()
            self.peers.remove(peer)

    def unchoked_peers(self):
        for peer in self.peers:
            if peer.peer_choked is False:
                return True
        return False

