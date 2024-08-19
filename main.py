import asyncio
import logging
import time

from parser import TorrentData
from torrent_statistics import TorrentStatistics
from tracker_manager import TrackerManager
from peer_interaction import PeerInteraction
from peer import Peer
from Message import RequestsMessage
from file_writer import FileWriter
from peer_manager import PeerManager


async def download_from_torrent_file(filename):
    torrent_file = TorrentData(filename)
    torrent_statistics = TorrentStatistics(torrent_file.total_length)
    logging.info(f"Total length: {torrent_file.total_length}, Segment length: {torrent_file.segment_length}, Total segments {torrent_file.total_segments}")

    pi = PeerInteraction(torrent_file)
    pi.start()

    async with TrackerManager(torrent_file, torrent_statistics) as trackers_manager:
        logging.info(f"Started tracker manager, active trackers: {', '.join([tracker.url for tracker in trackers_manager.tracker_clients])}")
        trackers_manager.create_peers_update_task()
        logging.info("Created peers update task")

        while True:
            if not trackers_manager.available_peers.empty():
                new_peer = trackers_manager.available_peers.get_nowait()
                new_peer = Peer(ip=new_peer[0], port=new_peer[1], number_of_pieces=torrent_file.total_segments)
                if new_peer.connect():
                    logging.info(f"New peer - {(new_peer.ip, new_peer.port)}")
                    pi.add_peer([new_peer])

                    f = False
                    for _ in range(200):
                        time.sleep(.01)
                        if any(new_peer.bitfield):
                            f = True
                            break
                    if f:
                        break

            await asyncio.sleep(.01)

        new_peer.send_message_to_peer(RequestsMessage(0, 0, 7100).encode())
        logging.info("Send request")

        while True:
            pass


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(download_from_torrent_file("torrent_files/test.torrent"))
