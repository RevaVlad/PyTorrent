from .parser import TorrentData
from .tracker_manager import TrackerManager
from .segment_writer import SegmentWriter
from .peer_manager import PeerManager

if __name__ == '__main__':
    torrent_file = TorrentData("nobody.torrent")
    trackers_manager = TrackerManager(torrent_file)
    segment_writer = SegmentWriter(torrent_file)
    peers_manager = PeerManager(torrent_file, trackers_manager, segment_writer)