import asyncio
import hashlib
import logging
from asyncio import Queue
from tracker_client import TrackerClient, TrackerEvent
from contextlib import suppress


class TrackerManager:
    PORT = 6880
    MAX_PEERS = 0

    def __init__(self, torrent_data, torrent_statistics):
        self.torrent_name = torrent_data.torrent_name
        self.tracker_clients = []
        self.info_hash = torrent_data.info_hash
        self.peer_id = self._create_peer_id()
        self.available_peers = Queue(self.MAX_PEERS)
        self.segment_info = torrent_statistics

        self.update_task = None

        for url in torrent_data.trackers:
            if not url.startswith('http') and not url.startswith('udp'):
                logging.error(f'Неверный трекер: {url}')
                continue
            self._add_tracker(url)

    def _create_peer_id(self):
        return '-PC0001-' + hashlib.sha1(self.info_hash).digest().hex()[:12]

    def _add_tracker(self, url):
        self.tracker_clients.append(TrackerClient(url, self.info_hash, self.peer_id, self.PORT, self.segment_info))

    async def __aenter__(self):
        bad_trackers = []
        for tracker in self.tracker_clients:
            try:
                await tracker.make_request(TrackerEvent.STARTED)
            except (ConnectionError, NotImplementedError) as e:
                logging.error(str(e))
                bad_trackers.append(tracker)
            except asyncio.TimeoutError as e:
                logging.error(f"Timeout error for tracker: {tracker.url}")
                bad_trackers.append(tracker)

        for bad_tracker in bad_trackers:
            self.tracker_clients.remove(bad_tracker)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.update_task:
            self.update_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.update_task

        for tracker in self.tracker_clients:
            await tracker.close()
        if exc_type is not None:
            logging.error(f'Got exception of type - "{exc_type}", with value - "{exc_val}" while working with trackers')

    async def _update_peers(self):
        while True:
            server_requests = [tracker.make_request(TrackerEvent.CHECK)
                               for tracker in self.tracker_clients]

            try:
                await asyncio.gather(*server_requests)

                for tracker in self.tracker_clients:
                    while not tracker.new_peers.empty():
                        peer = tracker.new_peers.get_nowait()
                        self.available_peers.put_nowait(peer)

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logging.info("Canceled peers updating task")
                break

    def create_peers_update_task(self):
        self.update_task = asyncio.create_task(self._update_peers())
        logging.info("Created peer updation task")
