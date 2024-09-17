import logging

import pytest
from unittest.mock import MagicMock, AsyncMock
from segment_downloader import SegmentDownloader, Segment
from block import Block
from peer_connection import PeerConnection
from pubsub import pub


@pytest.fixture
def torrent_data():
    mock_torrent_data = MagicMock()
    mock_torrent_data.segment_length = 1024
    mock_torrent_data.total_segments = 5
    mock_torrent_data.total_length = 5000
    mock_torrent_data.segments_hash = [b''] * 5
    return mock_torrent_data


@pytest.fixture
def file_writer():
    mock_file_writer = AsyncMock()
    return mock_file_writer


@pytest.fixture
def torrent_statistics():
    mock_torrent_statistics = MagicMock()
    return mock_torrent_statistics


@pytest.fixture
def peers():
    mock_peer1 = MagicMock(PeerConnection)
    mock_peer1.ip = "192.168.1.1"
    mock_peer1.is_active = True
    mock_peer1.send_message_to_peer = AsyncMock(return_value=True)
    mock_peer1.receive_event = "peer1_receive_event"

    mock_peer2 = MagicMock(PeerConnection)
    mock_peer2.ip = "192.168.1.2"
    mock_peer2.is_active = True
    mock_peer2.send_message_to_peer = AsyncMock(return_value=True)
    mock_peer2.receive_event = "peer2_receive_event"

    return [mock_peer1, mock_peer2]


@pytest.fixture
def segment_downloader(torrent_data, file_writer, torrent_statistics, peers):
    return SegmentDownloader(Segment(0), torrent_data=torrent_data, file_writer=file_writer,
                             torrent_statistics=torrent_statistics, peers=peers)


class TestSegmentDownloader:
    @pytest.mark.asyncio
    async def test_download_segment_failed_due_to_hash(self, segment_downloader, file_writer, torrent_data, monkeypatch):
        mock_hash = MagicMock()
        mock_hash.digest.return_value = b'\xFF' * 20  # Simulate wrong hash
        monkeypatch.setattr('hashlib.sha1', lambda data: mock_hash)

        segment_downloader.downloaded_blocks = {Block(0, i * Block.BLOCK_LENGTH, Block.BLOCK_LENGTH) for i in range(5)}
        for block in segment_downloader.downloaded_blocks:
            block.data = b'A' * Block.BLOCK_LENGTH

        await segment_downloader._download_segment()

        file_writer.write_segment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_tasks_completion(self, segment_downloader, peers):
        block = Block(0, 0, Block.BLOCK_LENGTH)
        block.status = Block.Missing
        peer = peers[0]

        segment_downloader.tasks[peer].add(block)

        segment_downloader.check_tasks_completion()

        assert block in segment_downloader.missing_blocks
        assert block not in segment_downloader.tasks[peer]
        assert segment_downloader.peers_strikes[peer] == 1

    @pytest.mark.asyncio
    async def test_request_block_success(self, segment_downloader, peers, monkeypatch):
        block = Block(0, 0, Block.BLOCK_LENGTH)
        peer = peers[0]

        monkeypatch.setattr(Block, 'change_status_to_missing', MagicMock())

        await segment_downloader.request_block(block, peer)

        assert block.status == Block.Pending
        assert block in segment_downloader.tasks[peer]

    @pytest.mark.asyncio
    async def test_on_receive_block(self, segment_downloader, peers):
        peer = peers[0]
        request = MagicMock()
        request.index = 0
        request.byte_offset = 0
        request.data = b'fake_data'

        block = Block(0, 0, Block.BLOCK_LENGTH)
        segment_downloader.tasks[peer].add(block)

        segment_downloader.on_receive_block(request=request, peer=peer)

        assert block in segment_downloader.downloaded_blocks
        assert block not in segment_downloader.tasks[peer]

    def test_on_receive_block_fail(self, segment_downloader, caplog):
        with caplog.at_level(logging.ERROR):
            segment_downloader.on_receive_block()
            assert 'Сообщение пусто' in caplog.text
            caplog.clear()
            segment_downloader.on_receive_block("request")
            assert 'Не указан пир' in caplog.text

    @pytest.mark.asyncio
    async def test_check_peers_connection_active_peer(self, segment_downloader, peers):
        peer = peers[0]
        peer.is_active = True
        segment_downloader.peers_strikes[peer] = 2
        segment_downloader.tasks[peer] = set()
        peer.close = AsyncMock()

        await segment_downloader.check_peers_connection()

        peer.close.assert_not_awaited()
        assert peer in segment_downloader.peers_strikes
        assert peer in segment_downloader.tasks

    @pytest.mark.asyncio
    async def test_check_peers_connection_inactive_peer(self, segment_downloader, peers, monkeypatch):
        peer = peers[1]
        peer.is_active = False
        segment_downloader.peers_strikes[peer] = 0
        segment_downloader.tasks[peer] = set()

        peer.close = AsyncMock()
        mock_send_message = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(pub, 'sendMessage', mock_send_message)

            await segment_downloader.check_peers_connection()

            peer.close.assert_awaited_once()
            assert peer not in segment_downloader.peers_strikes
            assert peer not in segment_downloader.tasks

            mock_send_message.assert_called_once_with(segment_downloader.peer_deletion_event,
                                                      segment_downloader=segment_downloader)




    @pytest.mark.asyncio
    async def test_check_tasks_completion_block_retrieved(self, segment_downloader, peers, monkeypatch):
        peer = peers[0]
        block = MagicMock()
        block.status = Block.Retrieved
        segment_downloader.tasks[peer] = {block}

        mock_downloaded_blocks = MagicMock()
        mock_downloaded_blocks.add = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(segment_downloader, 'downloaded_blocks', mock_downloaded_blocks)

            segment_downloader.check_tasks_completion()
            assert block not in segment_downloader.tasks[peer]

            mock_downloaded_blocks.add.assert_called_once_with(block)
            assert segment_downloader.peers_strikes[peer] == 0

    def test_add_peer(self, segment_downloader, monkeypatch):
        peer = MagicMock()
        peer.receive_event = "peer_event"

        mock_subscribe = MagicMock()
        monkeypatch.setattr(pub, 'subscribe', mock_subscribe)

        segment_downloader.add_peer(peer)
        assert segment_downloader.peers_strikes[peer] == 0
        assert segment_downloader.tasks[peer] == set()
        mock_subscribe.assert_called_once_with(segment_downloader.on_receive_block, peer.receive_event)

    from unittest.mock import MagicMock

    def test_close(self, segment_downloader, monkeypatch):
        block1 = MagicMock()
        block1.status = Block.Pending
        block2 = MagicMock()
        block2.status = Block.Retrieved

        peer = MagicMock()
        segment_downloader.tasks[peer] = {block1, block2}

        mock_downloading_task = MagicMock()
        segment_downloader.downloading_task = mock_downloading_task

        segment_downloader.close()
        block1.close.assert_called_once()
        block2.close.assert_not_called()
        mock_downloading_task.cancel.assert_called_once()
