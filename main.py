import asyncio
import logging
import pickle
import sys
import aioconsole

from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from torrent_downloader import Downloader
from file_writer import FileWriter
from pathlib import Path
from peer_connection import PeerConnection
from priority_queue import PriorityQueue
from requests_receiver import RequestsReceiver


class TorrentApplication:
    PICKLE_FILENAME = 'current_torrents.pickle'

    def __init__(self):
        self.torrents = []
        self.torrent_downloaders = []
        self.request_receiver = RequestsReceiver()

    def add_peer_by_info_hash(self, peer, info_hash):
        for td in self.torrent_downloaders:
            if td.torrent.info_hash == info_hash:
                peer.initiate_bitfield(td.torrent.total_segments)
                td.add_peer(peer)

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
        self.torrents.append((torrent_data, destination, torrent_statistics))  # delete torrent_stat?
        logging.info(
            f"Total length: {torrent_data.total_length}, Segment length: {torrent_data.segment_length}, Total segments {torrent_data.total_segments}")

        with FileWriter(torrent_data, destination=destination) as file_writer:
            async with TrackerManager(torrent_data, torrent_statistics,
                                      self.request_receiver.port, use_local=True) as trackers_manager:
                trackers_manager.create_peers_update_task()

                logging.info("Created all objects")
                torrent_downloader = Downloader(torrent_data,
                                                file_writer,
                                                torrent_statistics,
                                                trackers_manager.available_peers)
                self.torrent_downloaders.append(torrent_downloader)
                await torrent_downloader.download_torrent()

    def close(self):
        self.torrent_downloader.cancel()

    @staticmethod
    async def queue_update_task(source_queues: list[asyncio.Queue], queue_target: PriorityQueue, priority=True):
        while True:
            for index, queue in enumerate(source_queues):
                if not queue.empty():
                    queue_target.push(index if priority else 0, queue.get_nowait())

            await asyncio.sleep(.001)


if __name__ == '__main__':
    # logging.basicConfig(level=logging.FATAL)
    logging.basicConfig(level=logging.INFO)

    data = TorrentData("torrent_files/test.torrent")
    client = TorrentApplication()
    asyncio.run(client.download(data, Path('./downloaded'), TorrentStatistics(data.total_length, data.total_segments)))
