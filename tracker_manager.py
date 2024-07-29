import asyncio
import hashlib
import logging
from asyncio import Queue
from tracker_client import TrackerClient, TrackerEvent


class TrackerManager:
    PORT = 6880
    MAX_PEERS = 0

    def __init__(self, torrent_data, torrent_statistics):
        self.tracker_clients = []
        self.info_hash = torrent_data.info_hash
        self.peer_id = self._create_peer_id()
        self.available_peers = Queue(self.MAX_PEERS)
        self.segment_info = torrent_statistics

        for url in torrent_data.trackers:
            if not url.startswith('http'):
                continue
            self._add_tracker(url)

    def _create_peer_id(self):
        return '-PC0001-' + hashlib.sha1(self.info_hash).digest().hex()[:12]

    def _add_tracker(self, url):
        self.tracker_clients.append(TrackerClient(url, self.info_hash, self.peer_id, self.PORT))

    async def initiate_trackers(self):
        bad_trackers = []
        for tracker in self.tracker_clients:
            try:
                await tracker.make_request(self.segment_info, TrackerEvent.STARTED)
            except (ConnectionError, NotImplementedError) as e:
                logging.error(str(e))
                bad_trackers.append(tracker)
            except asyncio.TimeoutError as e:
                logging.error(f"Timeout error for tracker: {tracker.url}")
                bad_trackers.append(tracker)

        for bad_tracker in bad_trackers:
            self.tracker_clients.remove(bad_tracker)

    async def update_peers(self):
        server_requests = [tracker.make_request(self.segment_info, TrackerEvent.CHECK)
                           for tracker in self.tracker_clients]
        await asyncio.gather(*server_requests)

        for tracker in self.tracker_clients:
            while not tracker.new_peers.empty():
                self.available_peers.put_nowait(tracker.new_peers.get_nowait())
