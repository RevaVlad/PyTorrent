import asyncio
import logging
import pickle
import sys

from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from torrent_downloader import Downloader
from file_writer import FileWriter
from pathlib import Path
from priority_queue import PriorityQueue
from requests_receiver import RequestsReceiver
from pubsub import pub


class TorrentApplication:
    PICKLE_FILENAME = 'current_torrents.pickle'

    def __init__(self):
        self.torrents = []
        self.torrent_downloaders = []

        self.request_receiver = RequestsReceiver()
        self.server_started = False
        pub.subscribe(self.add_peer_by_info_hash, self.request_receiver.NEW_PEER_EVENT)

    def add_peer_by_info_hash(self, peer, info_hash):
        asyncio.create_task(self._add_peer_coro(peer, info_hash))

    async def _add_peer_coro(self, peer, info_hash):
        for td in self.torrent_downloaders:
            if td.torrent.info_hash == info_hash:
                await peer.initiate_bitfield(td.torrent.total_segments, td.torrent_statistics.bitfield)
                await td.add_peer(peer)

    def get_previous_torrents(self):
        file = Path(sys.path[0]) / self.PICKLE_FILENAME
        if file.exists():
            with open(file, 'rb') as f:
                torrents = pickle.load(f)
            return torrents
        return []

    def save_current_torrents(self):
        project_directory = Path(sys.path[0])
        location = project_directory / self.PICKLE_FILENAME
        if not location.exists():
            location.open('w').close()
        with open(location, 'wb') as f:
            pickle.dump(self.torrents, f)

    async def download(self, torrent_data, destination, torrent_statistics):
        if not self.server_started:
            self.request_receiver.start_server()
            self.server_started = True

        self.torrents.append((torrent_data, destination, torrent_statistics))  # delete torrent_stat?
        logging.info(
            f"Total length: {torrent_data.total_length}, Segment length: {torrent_data.segment_length}, Total segments {torrent_data.total_segments}")

        with FileWriter(torrent_data, destination=destination) as file_writer:
            async with TrackerManager(torrent_data, torrent_statistics,
                                      self.request_receiver.port, use_local=False, use_http=True) as trackers_manager:
                trackers_manager.create_peers_update_task()

                logging.info("Created all objects")
                torrent_downloader = Downloader(torrent_data,
                                                file_writer,
                                                torrent_statistics,
                                                trackers_manager.available_peers)
                self.torrent_downloaders.append(torrent_downloader)
                await torrent_downloader.download_torrent()

    def close(self):
        self.request_receiver.close()
        for td in self.torrent_downloaders:
            td.close()

    @staticmethod
    async def queue_update_task(source_queues: list[asyncio.Queue], queue_target: PriorityQueue, priority=True):
        while True:
            for index, queue in enumerate(source_queues):
                if not queue.empty():
                    queue_target.push(index if priority else 0, queue.get_nowait())

            await asyncio.sleep(.001)


if __name__ == '__main__':
    async def main():
        files = ["torrent_files/test.torrent"]
                 # "torrent_files/nobody.torrent"]
        tds = [TorrentData(file) for file in files]

        client = TorrentApplication()
        coroutines = [client.download(td,
                                      Path('./downloaded'),
                                      TorrentStatistics(td.total_length, td.total_segments)) for td in tds]

        tasks = [asyncio.create_task(coro) for coro in coroutines]
        await asyncio.gather(*tasks)


    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
