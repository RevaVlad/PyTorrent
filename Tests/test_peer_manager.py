import logging
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from tracker_manager import TrackerManager, HttpTrackerClient, BadTorrentTrackers
import tracker_client


@pytest.fixture
def torrent_data():
    return AsyncMock(
        torrent_name="test_torrent",
        info_hash=b'\x12' * 20,
        total_segments=100
    )


@pytest.fixture
def torrent_statistics():
    return AsyncMock()


@pytest.fixture
def tracker_manager(torrent_data, torrent_statistics):
    return TrackerManager(torrent_data, torrent_statistics, port=6881)


class TestTrackerManager:
    @pytest.mark.asyncio
    async def test_tracker_manager_aenter(self, monkeypatch, tracker_manager):
        async def mock_make_request(event):
            pass

        with monkeypatch.context() as m:
            mock_http_tracker = AsyncMock(HttpTrackerClient)
            mock_http_tracker.make_request = AsyncMock(side_effect=mock_make_request)

            m.setattr('tracker_manager.HttpTrackerClient', mock_http_tracker)
            tracker_manager.tracker_clients.append(mock_http_tracker)

            async with tracker_manager:
                mock_http_tracker.make_request.assert_called_once_with(tracker_client.TrackerEvent.STARTED)

    @pytest.mark.asyncio
    async def test_aenter_fail(self, tracker_manager):
        failing_tracker = AsyncMock()
        failing_tracker.make_request = AsyncMock(side_effect=ConnectionError)
        failing_tracker_second = AsyncMock()
        failing_tracker_second.make_request = AsyncMock(side_effect=asyncio.TimeoutError)

        tracker_manager.tracker_clients.append(failing_tracker)
        tracker_manager.tracker_clients.append(failing_tracker_second)

        with pytest.raises(BadTorrentTrackers) as excinfo:
            async with tracker_manager:
                pass

        assert str(excinfo.value) == "Torrent file had no stable trackers"
        assert failing_tracker in excinfo.value.bad_trackers
        assert len(tracker_manager.tracker_clients) == 0

    @pytest.mark.asyncio
    async def test_aexit(self, tracker_manager, caplog):
        mock_tracker = AsyncMock()
        mock_tracker.close = AsyncMock()
        mock_update_task = AsyncMock()
        mock_update_task.cancel = AsyncMock()
        mock_update_task.__await__ = AsyncMock(return_value=iter([None]))
        tracker_manager.update_task = mock_update_task
        tracker_manager.tracker_clients = [mock_tracker]

        tracker_manager.create_peers_update_task()

        assert isinstance(tracker_manager.update_task, asyncio.Task)

        await tracker_manager.__aexit__(None, None, None)
        mock_tracker.close.assert_called_once()
        assert len(caplog.records) == 0

    @pytest.mark.asyncio
    async def test_aexit_with_exception(self, tracker_manager, caplog):
        mock_tracker = AsyncMock()
        mock_tracker.close = AsyncMock()
        mock_update_task = AsyncMock()
        mock_update_task.cancel = AsyncMock()
        mock_update_task.__await__ = AsyncMock(return_value=iter([None]))
        tracker_manager.update_task = mock_update_task
        tracker_manager.tracker_clients = [mock_tracker]
        tracker_manager.create_peers_update_task()

        assert isinstance(tracker_manager.update_task, asyncio.Task)

        exc_type = ValueError
        exc_val = ValueError("Test exception")
        await tracker_manager.__aexit__(exc_type, exc_val, None)
        mock_tracker.close.assert_called_once()

        assert f'Got exception of type - "{exc_type}", with value - "{exc_val}" while working with trackers' in caplog.text

    @pytest.mark.asyncio
    async def test_update_peers(self, monkeypatch, tracker_manager):
        async def mock_make_request(event):
            pass

        async def mock_get_nowait():
            return ("127.0.0.1", 6881)

        with monkeypatch.context() as m:
            mock_http_tracker = AsyncMock(HttpTrackerClient)

            mock_new_peers = AsyncMock()
            mock_new_peers.empty.return_value = False
            mock_new_peers.get_nowait = AsyncMock(side_effect=mock_get_nowait)

            mock_http_tracker.make_request = AsyncMock(side_effect=mock_make_request)
            mock_http_tracker.new_peers = mock_new_peers

            m.setattr('tracker_manager.HttpTrackerClient', mock_http_tracker)
            tracker_manager.tracker_clients.append(mock_http_tracker)

            tracker_manager.create_peers_update_task()
            await asyncio.sleep(1)

            mock_http_tracker.make_request.assert_called_with(tracker_client.TrackerEvent.CHECK)
            assert tracker_manager.available_peers.qsize() == 0

            tracker_manager.update_task.cancel()

    @pytest.mark.asyncio
    async def test_create_peers_update_task(self, monkeypatch, tracker_manager):
        with monkeypatch.context() as m:
            mock_update_peers = AsyncMock()
            m.setattr(tracker_manager, '_update_peers', mock_update_peers)

            tracker_manager.create_peers_update_task()

            assert tracker_manager.update_task is not None
            assert mock_update_peers.call_count == 1

    def test_add_tracker_http(self, monkeypatch, tracker_manager):
        class MockHttpTrackerClient:
            pass

        with monkeypatch.context() as m:
            m.setattr(tracker_client, 'HttpTrackerClient', MockHttpTrackerClient)
            tracker_manager._add_tracker('http://tracker.example.com')
            assert len(tracker_manager.tracker_clients) == 1
            assert tracker_manager.tracker_clients[0].url == 'http://tracker.example.com'

    def test_add_tracker_local(self, tracker_manager):
        tracker_manager._add_tracker('local')
        assert len(tracker_manager.tracker_clients) == 1
        assert type(tracker_manager.tracker_clients[0]) is tracker_client.LocalConnections