import asyncio
import logging
import pickle
import sys
import aioconsole

from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from torrent_downloader import TorrentDownloader
from file_writer import FileWriter
from pathlib import Path
from requests_receiver import RequestsReceiver
from priority_queue import PriorityQueue


async def queue_update_task(source_queues: list[asyncio.Queue], queue_target: PriorityQueue, priority=True):
    while True:
        for index, queue in enumerate(source_queues):
            if not queue.empty():
                queue_target.push(index if priority else 0, queue.get_nowait())

        await asyncio.sleep(.001)


async def download_from_torrent_file(torrent_file: TorrentData, destination: Path, torrent_statistics: TorrentStatistics):
    logging.info(
        f"Total length: {torrent_file.total_length}, Segment length: {torrent_file.segment_length}, Total segments {torrent_file.total_segments}")

    requests_receiver = RequestsReceiver(torrent_file)
    with FileWriter(torrent_file, destination=destination) as file_writer:
        async with TrackerManager(torrent_file, torrent_statistics, requests_receiver.port) as trackers_manager:
            trackers_manager.create_peers_update_task()
            logging.info(f"Port: {requests_receiver.port}")
            requests_receiver.start_server()

            logging.info("Created all objects")
            # trackers_manager.create_peers_update_task()
            torrent_downloader = TorrentDownloader(torrent_file,
                                                   file_writer,
                                                   torrent_statistics,
                                                   trackers_manager.available_peers)
            await torrent_downloader.download_torrent()
            while True:
                await asyncio.sleep(.1)
            torrent_downloader.close()

    request_receiver.close()
    return torrent_downloader, requests_receiver


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


async def get_input_from_console():
    user_input = await aioconsole.ainput("Введите команду (download <Path_to_torrent> <Destination>): ")
    data = user_input.split()
    if data[0] == 'download':
        return data[1], Path(data[2])


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


if __name__ == '__main__':
    # logging.basicConfig(level=logging.FATAL)
    logging.basicConfig(level=logging.INFO)

    data = TorrentData("torrent_files/test.torrent")
    asyncio.run(download_from_torrent_file(data,
                                           Path('./downloaded'),
                                           TorrentStatistics(data.total_length, data.total_segments)))
