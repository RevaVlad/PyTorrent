from torrent_statistics import TorrentStatistics


class TestTorrentStatistics:
    def test_update_downloaded(self):
        torrent_stat = TorrentStatistics(200, 10)
        torrent_stat.update_downloaded(20)
        assert torrent_stat.downloaded == 20
        assert torrent_stat.left == 180

    def test_update_uploaded(self):
        torrent_stat = TorrentStatistics(200, 10)
        torrent_stat.update_uploaded(20)
        assert torrent_stat.uploaded == 20

    def test_bitfield_update(self):
        torrent_stat = TorrentStatistics(200, 10)
        torrent_stat.update_bitfield(1, True)
        assert torrent_stat.bitfield[1] == True
