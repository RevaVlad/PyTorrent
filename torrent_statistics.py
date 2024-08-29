import bitstring


class TorrentStatistics:

    def __init__(self, left, total_segments, downloaded=0, uploaded=0):
        self._downloaded = downloaded
        self._uploaded = uploaded
        self._left = left
        self._bitfield = bitstring.BitArray(total_segments)

    def update_downloaded(self, size):
        self._downloaded += size
        self._left -= size

    def update_uploaded(self, size):
        self._uploaded += size

    def update_bitfield(self, index: int, value: bool):
        self._bitfield[index] = value

    @property
    def downloaded(self):
        return self._downloaded

    @property
    def left(self):
        return self._left

    @property
    def uploaded(self):
        return self._uploaded

    @property
    def bitfield(self):
        return self._bitfield
