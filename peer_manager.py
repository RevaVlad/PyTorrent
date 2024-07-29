import asyncio


class PeerManager:

    def __init__(self, torrent, tracker_manager, segment_writer):
        pass


class TorrentStatistics:

    def __init__(self, left, downloaded=0, uploaded=0):
        self._downloaded = downloaded
        self._uploaded = uploaded
        self._left = left

    def update_downloaded(self, size):
        self._downloaded += size
        self._left -= size

    def update_uploaded(self, size):
        self._uploaded += size

    @property
    def downloaded(self):
        return self._downloaded

    @property
    def left(self):
        return self._left

    @property
    def uploaded(self):
        return self._uploaded
