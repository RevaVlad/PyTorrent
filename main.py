import asyncio
import logging
import time

from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from torrent_downloader import TorrentDownloader
from file_writer import FileWriter
from pathlib import Path


async def download_from_torrent_file(filename):
    torrent_file = TorrentData(filename)
    torrent_statistics = TorrentStatistics(torrent_file.total_length)
    logging.info(
        f"Total length: {torrent_file.total_length}, Segment length: {torrent_file.segment_length}, Total segments {torrent_file.total_segments}")

    with FileWriter(torrent_file, destination=Path('./downloaded')) as file_writer:
        async with TrackerManager(torrent_file, torrent_statistics) as trackers_manager:
            logging.info("Created all objects")
            trackers_manager.create_peers_update_task()
            torrent_downloader = TorrentDownloader(torrent_file,
                                                   file_writer,
                                                   torrent_statistics,
                                                   trackers_manager.available_peers)
            await torrent_downloader.download_torrent()
            torrent_downloader.close()

    logging.info(f"Download completed!!!")


def check_segment(filename, segment_id):
    torrent_file = TorrentData(filename)
    with FileWriter(torrent_file, destination=Path('./downloaded')) as file_writer:
        return asyncio.run(file_writer.read_segment(segment_id))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # torrent_file = TorrentData('torrent_files/test.torrent')
    # res = check_segment('torrent_files/test.torrent', 0)
    # logging.info(f"Expected segment len: {len(res)}")
    asyncio.run(download_from_torrent_file("torrent_files/test.torrent"), debug=True)
