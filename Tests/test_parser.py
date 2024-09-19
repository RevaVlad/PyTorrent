import pytest
from unittest import mock
import hashlib
import bencode
from math import ceil
from parser import TorrentData


@pytest.fixture
def single_file_torrent_data():
    return {
        'announce': 'http://tracker.example.com/announce',
        'info': {
            'name': 'testfile',
            'piece length': 16384,
            'pieces': b'12345678901234567890' * 3,
            'length': 49152
        }
    }


@pytest.fixture
def multi_file_torrent_data():
    return {
        'announce': 'http://tracker.example.com/announce',
        'info': {
            'name': 'testdir',
            'piece length': 16384,
            'pieces': b'abcdefghijabcdefghij' * 3,
            'files': [
                {'length': 20000, 'path': ['file1']},
                {'length': 29152, 'path': ['file2']}
            ]
        }
    }


@pytest.fixture
def mock_open_bencode(monkeypatch, single_file_torrent_data):
    with monkeypatch.context() as m:
        mock_file = mock.mock_open(read_data=b"mocked file content")
        m.setattr("builtins.open", mock_file)

        mock_bdecode = mock.Mock(return_value=single_file_torrent_data)
        m.setattr(bencode, "bdecode", mock_bdecode)

        yield mock_file, mock_bdecode


@pytest.fixture
def mock_open_bencode_multi(monkeypatch, multi_file_torrent_data):
    with monkeypatch.context() as m:
        mock_file = mock.mock_open(read_data=b"mocked file content")
        m.setattr("builtins.open", mock_file)

        mock_bdecode = mock.Mock(return_value=multi_file_torrent_data)
        m.setattr(bencode, "bdecode", mock_bdecode)

        yield mock_file, mock_bdecode


class TestTorrentData:
    def test_torrent_data_single_file(self, mock_open_bencode, single_file_torrent_data):
        torrent = TorrentData("mocked_file.torrent")

        assert torrent.torrent_name == 'testfile'
        assert torrent.segment_length == 16384
        assert torrent.segments_hash == [b'12345678901234567890', b'12345678901234567890', b'12345678901234567890']
        assert torrent.info_hash == hashlib.sha1(bencode.bencode(single_file_torrent_data['info'])).digest()
        assert torrent.total_length == 49152
        assert torrent.total_segments == ceil(49152 / 16384)
        assert torrent.files == [{'length': 49152, 'path': ['testfile']}]

    def test_torrent_data_multi_file(self, mock_open_bencode_multi, multi_file_torrent_data):
        torrent = TorrentData("mocked_file.torrent")

        assert torrent.torrent_name == 'testdir'
        assert torrent.segment_length == 16384
        assert torrent.segments_hash == [b'abcdefghijabcdefghij', b'abcdefghijabcdefghij', b'abcdefghijabcdefghij']
        assert torrent.info_hash == hashlib.sha1(bencode.bencode(multi_file_torrent_data['info'])).digest()
        assert torrent.total_length == 49152
        assert torrent.total_segments == ceil(49152 / 16384)
        assert torrent.files == [{'length': 20000, 'path': ['file1']}, {'length': 29152, 'path': ['file2']}]

    def test_get_announce_list(self, mock_open_bencode, single_file_torrent_data):
        torrent = TorrentData("mocked_file.torrent")
        assert torrent._get_announce_list(single_file_torrent_data) == ['http://tracker.example.com/announce']

    def test_get_files_list(self, mock_open_bencode, single_file_torrent_data):
        torrent = TorrentData("mocked_file.torrent")
        assert torrent._get_files_list(single_file_torrent_data['info']) == [{'length': 49152, 'path': ['testfile']}]