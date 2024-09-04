import asyncio
import logging
import pickle
import sys
import aioconsole
import time

from progress.bar import IncrementalBar
from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from torrent_downloader import TorrentDownloader
from file_writer import FileWriter
from pathlib import Path


async def tests(torrent_downloader):
    while True:
        # logging.info( f"Active peers: {len(torrent_downloader.active_peers)}, {[x[0] for x in
        # torrent_downloader.available_segments[:10]]}")
        await asyncio.sleep(3)


async def update_progress_bar(bar, torrent_stat: TorrentStatistics):
    progress = 0
    while not bar.remaining == 0:
        for i in range(progress, torrent_stat.downloaded, 100):
            bar.index = i
            bar.update()
            await asyncio.sleep(.001)
        progress = bar.index = torrent_stat.downloaded
        bar.update()
        await asyncio.sleep(1)
    bar.finish()


async def download_from_torrent_file(filename, destination: Path):
    torrent_file = TorrentData(filename)
    torrent_statistics = TorrentStatistics(torrent_file.total_length, torrent_file.total_segments)
    logging.info(
        f"Total length: {torrent_file.total_length}, Segment length: {torrent_file.segment_length}, Total segments {torrent_file.total_segments}")

    progress_bar = IncrementalBar(f'{Path(filename).name} progress', max=torrent_statistics.left)
    bar_task = asyncio.create_task(update_progress_bar(progress_bar, torrent_statistics))

    with FileWriter(torrent_file, destination=destination) as file_writer:
        async with TrackerManager(torrent_file, torrent_statistics) as trackers_manager:
            logging.info("Created all objects")
            trackers_manager.create_peers_update_task()
            torrent_downloader = TorrentDownloader(torrent_file,
                                                   file_writer,
                                                   torrent_statistics,
                                                   trackers_manager.available_peers)
            asyncio.create_task(tests(torrent_downloader))
            await torrent_downloader.download_torrent()
            torrent_downloader.close()

    logging.info(f"Download completed!!!")


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
    if not (location).exists():
        location.open('w').close()
    with open(location, 'wb') as f:
        pickle.dump(torrents, f)


def check_segment(filename, segment_id):
    torrent_file = TorrentData(filename)
    with FileWriter(torrent_file, destination=Path('./downloaded')) as file_writer:
        return asyncio.run(file_writer.read_segment(segment_id))


if __name__ == '__main__':
    #logging.basicConfig(level=logging.FATAL)
    logging.basicConfig(level=logging.INFO)
    asyncio.run(download_from_torrent_file("torrent_files/file.torrent", Path('./downloaded')), debug=True)
    #asyncio.run(main_loop())
