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
from requests_receiver import RequestsReceiver
from priority_queue import PriorityQueue


class Torrent:

    def __init__(self, td: TorrentData, destination, torrent_statistics):
        self.torrent_data = td
        self.destination = destination
        self.torrent_statistics = torrent_statistics

        self.torrent_downloader = None
        self._download_task = None

    def start_download(self):
        self._download_task = asyncio.create_task(self.download_from_torrent_file())

    def cancel_download(self):
        self._download_task.cancel()
        self.torrent_downloader.cancel()

    async def download_from_torrent_file(self):
        logging.info(
            f"Total length: {self.torrent_data.total_length}, Segment length: {self.torrent_data.segment_length}, Total segments {self.torrent_data.total_segments}")

        requests_receiver = RequestsReceiver(self.torrent_data)
        with FileWriter(self.torrent_data, destination=self.destination) as file_writer:
            async with TrackerManager(self.torrent_data, self.torrent_statistics,
                                      requests_receiver.port, use_local=True) as trackers_manager:
                trackers_manager.create_peers_update_task()
                logging.info(f"Port: {requests_receiver.port}")

                logging.info("Created all objects")
                self.torrent_downloader = Downloader(self.torrent_data,
                                                     file_writer,
                                                     self.torrent_statistics,
                                                     trackers_manager.available_peers)
                await self.torrent_downloader.download_torrent()

    @staticmethod
    async def queue_update_task(source_queues: list[asyncio.Queue], queue_target: PriorityQueue, priority=True):
        while True:
            for index, queue in enumerate(source_queues):
                if not queue.empty():
                    queue_target.push(index if priority else 0, queue.get_nowait())

            await asyncio.sleep(.001)


if __name__ == '__main__':

    async def sleep(torrent):
        torrent.start_download()
        while True:
            await asyncio.sleep(1000)

    # logging.basicConfig(level=logging.FATAL)
    logging.basicConfig(level=logging.INFO)

    data = TorrentData("torrent_files/test.torrent")
    torrent = Torrent(data, Path('./downloaded'), TorrentStatistics(data.total_length, data.total_segments))
    asyncio.run(sleep(torrent))

'''
    async def main_loop():
        torrents = get_previous_torrents('current_torrents.pickle')
        torrent_tasks = [asyncio.create_task(download_from_torrent_file(location, destination)) for (location, destination)
                         in torrents]

        try:
            while True:
                logging.info(f"Active torrents: {torrents}")
                location, destination = await get_input_from_console()
                torrents.append((location, destination))
                torrent_tasks.append(asyncio.create_task(download_from_torrent_file(location, destination)))
        except asyncio.CancelledError:
            save_current_torrents('current_torrents.pickle', torrents)

    def get_previous_torrents(pickle_file_name):
        project_directory = Path(sys.path[0])
        if (project_directory / pickle_file_name).exists():
            with open(project_directory / pickle_file_name, 'rb') as f:
                torrents = pickle.load(f)
            return torrents
        return []


    def save_current_torrents(pickle_file_name, torrents):
        project_directory = Path(sys.path[0])
        location = project_directory / pickle_file_name
        if not location.exists():
            location.open('w').close()
        with open(location, 'wb') as f:
            pickle.dump(torrents, f)
    
    def check_segment(filename, segment_id):
        torrent_file = TorrentData(filename)
        with FileWriter(torrent_file, destination=Path('./downloaded')) as file_writer:
            return asyncio.run(file_writer.read_segment(segment_id))
'''
