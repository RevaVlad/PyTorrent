import asyncio
import logging

from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from file_writer import FileWriter
from peer_manager import PeerManager


async def download_from_torrent_file(filename):
    torrent_file = TorrentData(filename)
    torrent_statistics = TorrentStatistics(torrent_file.total_length)
    async with TrackerManager(torrent_file, torrent_statistics) as trackers_manager:
        logging.info(f"Started tracker manager, active trackers: {', '.join([tracker.url for tracker in trackers_manager.tracker_clients])}")
        trackers_manager.create_peers_update_task()
        logging.info("Created peers update task")

        for i in range(1000):
            if not trackers_manager.available_peers.empty():
                logging.info(f"New peer - {trackers_manager.available_peers.get_nowait()}")
            await asyncio.sleep(0.01)

    #peers_manager = PeerManager(torrent_file, trackers_manager, segment_writer)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(download_from_torrent_file("test.torrent"))
