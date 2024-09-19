from tracker_client import LocalConnections, HttpTrackerClient, TrackerEvent
from unittest.mock import AsyncMock
from struct import pack
import pytest
import asyncio
import socket
import logging


@pytest.fixture
def local_connection():
    return LocalConnections()


@pytest.fixture
def http_tracker():
    client = HttpTrackerClient(
        'http://example.com/announce',
        'info_hash',
        'peer_id',
        6881,
        AsyncMock(downloaded=123, uploaded=456, left=789)
    )
    return client


class TestTrackerClient:
    def test_decode_peer_data(self, http_tracker):
        pack_ip_and_port = socket.inet_aton('192.168.127.12') + pack('!H', 6881)
        ip, port = http_tracker._decode_peer_data(pack_ip_and_port)
        assert ip == '192.168.127.12'
        assert port == 6881

    def test_parse_response_failed(self, http_tracker):
        response = {
            'failure reason': 'Tracker unavailable'
        }

        with pytest.raises(ConnectionError, match='Unable to connect to'):
            http_tracker._parse_response(response)

    def test_parse_response_success_with_peer_list(self, http_tracker):
        response = {
            'interval': 1800,
            'min interval': 900,
            'tracker id': 'idid',
            'peers': [{'ip': '192.168.1.1', 'port': 6881}, {'ip': '192.168.1.2', 'port': 6881}]
        }

        http_tracker._parse_response(response)

        assert http_tracker.request_interval == 900
        assert http_tracker.tracker_id == 'idid'
        assert http_tracker._peers == {('192.168.1.1', 6881), ('192.168.1.2', 6881)}

    def test_parse_response_success(self, http_tracker):
        response = {
            'peers': socket.inet_aton('192.168.1.1') + pack('!H', 6881)
        }

        http_tracker._parse_response(response)
        assert http_tracker._peers == {('192.168.1.1', 6881)}

    @pytest.mark.asyncio
    async def test_close_http_tracker(self, http_tracker, monkeypatch):
        mock_make_request = AsyncMock()
        with monkeypatch.context() as m:
            m.setattr(http_tracker, 'make_request', mock_make_request)
            await http_tracker.close()
            assert mock_make_request.call_args[0][0] == TrackerEvent.STOPPED

    @pytest.mark.asyncio
    async def test_close_http_tracker_failed(self, http_tracker, monkeypatch, caplog):
        mock_make_request = AsyncMock(side_effect=asyncio.TimeoutError)
        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(http_tracker, 'make_request', mock_make_request)
                await http_tracker.close()
                assert 'Timeout error while close connection with tracker' in caplog.text

    @pytest.mark.asyncio
    async def test_add_peer_local(self, local_connection):
        await local_connection._add_peer('127.0.0.1')
        element = await local_connection.new_peers.get()
        assert element == ('127.0.0.1', 52656)
        assert local_connection.new_peers.empty()

    @pytest.mark.asyncio
    async def test_add_peer_repeat_local(self, local_connection):
        local_connection._peers.add('127.0.0.1')
        await local_connection._add_peer('127.0.0.1')
        assert local_connection.new_peers.empty()

    @pytest.mark.asyncio
    async def test_close_local(self, local_connection):
        await local_connection.close()
        assert True

    @pytest.mark.asyncio
    async def test_make_request(self, local_connection):
        local_connection._add_peer = AsyncMock()
        await local_connection.make_request(None)
        assert local_connection._add_peer.call_count == 200
        expected_calls = [local_connection.ip_start + '.' + str(i) for i in range(200)]
        actual_calls = [call.args[0] for call in local_connection._add_peer.call_args_list]
        assert actual_calls == expected_calls
