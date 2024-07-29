import asyncio
import logging

from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from file_writer import FileWriter
from peer_manager import PeerManager

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    torrent_file = TorrentData("test.torrent")
    torrent_statistics = TorrentStatistics(torrent_file.total_length)
    trackers_manager = TrackerManager(torrent_file, torrent_statistics)
    asyncio.run(trackers_manager.initiate_trackers(), debug=True)

    '''
    asyncio.run(trackers_manager.update_peers(), debug=True)
    while not trackers_manager.available_peers.empty():
        logging.info(trackers_manager.available_peers.get_nowait())
    '''

    #peers_manager = PeerManager(torrent_file, trackers_manager, segment_writer)
