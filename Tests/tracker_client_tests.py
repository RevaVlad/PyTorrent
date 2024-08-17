import asyncio
import logging

import httpx

import torrent_statistics
import pytest
import tracker_client
from pytest_httpx import HTTPXMock


@pytest.fixture
def info_hash():
    return b'\xd9\x84\xf6z\xf9\x91{!L\xd8\xb6\x04\x8a\xb5bL}\xf6\xa0z'


@pytest.fixture
def peer_id():
    return '-PC0001-38511c1ac470'


@pytest.fixture
def segment_info():
    return torrent_statistics.TorrentStatistics(19296724)


@pytest.fixture
def port():
    return 6880


@pytest.fixture
def peers(port):
    return [{'ip': 1, 'port': port},
            {'ip': 2, 'port': port}]


@pytest.fixture
def compact_peers():
    return


@pytest.fixture
def failure_response(peers):
    return {'failure reason': 'bad connection',
            'peers': peers,
            'interval': 60,
            'tracker id': 42}


@pytest.fixture
def good_response(peers):
    return {'interval': 60,
            'tracker id': 42,
            'peers': peers}


@pytest.fixture
def compact_response(compact_peers):
    return {'interval': 60,
            'tracker id': 42,
            'peers': compact_peers}


@pytest.fixture
def bad_tracker():
    return 'http://uniongang.org/announce.php?passkey=1'


@pytest.fixture
def good_tracker():
    return


class TestTrackerClient:

    def test_connection_error(self, bad_tracker, info_hash, peer_id, port, segment_info):
        client = tracker_client.TrackerClient(bad_tracker, info_hash, peer_id, port, segment_info)
        with pytest.raises(ConnectionError):
            asyncio.run(client.make_request(tracker_client.TrackerEvent.STARTED))

    def test_failure_in_response(self, good_tracker, info_hash, peer_id, port, segment_info, failure_response):
        client = tracker_client.TrackerClient(good_tracker, info_hash, peer_id, port, segment_info)
        with pytest.raises(ConnectionError):
            client._parse_response(failure_response)
        assert client.new_peers.empty()

    def test_response_parser(self, good_tracker, info_hash, peer_id, port, segment_info, good_response, peers):
        client = tracker_client.TrackerClient(good_tracker, info_hash, peer_id, port, segment_info)
        client._parse_response(good_response)
        assert not client.new_peers.empty()

        new_peers = [client.new_peers.get_nowait() for _ in range(len(peers))]
        for actual_peer, expected_peer in zip(new_peers, peers):
            assert actual_peer[0] == expected_peer['ip'] and actual_peer[1] == expected_peer['port']
            # assert actual_peer == (expected_peer['ip'], expected_peer['port'])

    '''
    def test_compact_response(self, good_tracker, info_hash, peer_id, port, segment_info, compact_response, peers):
        client = tracker_client.TrackerClient(good_tracker, info_hash, peer_id, port, segment_info)
        client._parse_response(compact_response)
        assert not client.new_peers.empty()

        new_peers = [client.new_peers.get_nowait() for _ in range(len(peers))]
        for actual_peer, expected_peer in zip(new_peers, peers):
            assert actual_peer[0] == expected_peer['ip'] and actual_peer[1] == expected_peer['port']
    '''

    def test_last_message(self, good_tracker, info_hash, peer_id, port, segment_info, caplog):
        caplog.set_level(logging.INFO)
        client = tracker_client.TrackerClient(good_tracker, info_hash, peer_id, port, segment_info)
        asyncio.run(client.close())
        assert "'event': 'stopped'" in caplog
