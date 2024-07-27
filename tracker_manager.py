import hashlib
import parser
from .tracker_client import TrackerClient
from asyncio import Queue


class TrackerManager:
    PORT = 6880
    MAX_PEERS = 0

    def __init__(self, torrent: parser.TorrentData):
        self.tracker_clients = []
        self.info_hash = torrent.info_hash
        self.peer_id = self._create_peer_id()
        self.available_peers = Queue(self.MAX_PEERS)

        for url in torrent.trackers:
            if not url.startswith('http'):
                continue
            self._add_tracker(url)

    def _create_peer_id(self):
        return hashlib.sha1(self.info_hash)

    def _add_tracker(self, url):
        self.tracker_clients.append(TrackerClient(url, self.info_hash, self.peer_id, self.PORT))

    async def update_peers(self):
        while not self.available_peers.full():
            for tracker in self.tracker_clients:
                self.available_peers.put_nowait(await tracker.new_peers.get())
