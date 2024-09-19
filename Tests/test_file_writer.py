from collections import deque

import pytest
import logging
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from file_writer import FileWriter, AsyncFile


@pytest.fixture
def async_file():
    return AsyncFile(
        MagicMock(spec=Path)
    )


@pytest.fixture
def file_writer(tmp_path):
    mock_torrent = MagicMock()
    mock_torrent.segment_length = 16384
    mock_torrent.torrent_name = 'mock_torrent'
    mock_torrent.files = [
        {'path': ['folder', 'file1.txt'], 'length': 1024},
        {'path': ['folder', 'file2.txt'], 'length': 2048},
    ]
    return FileWriter(mock_torrent, tmp_path)


class TestFileWriter:
    def test_enter(self, async_file, monkeypatch):
        mock_open = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(async_file, 'open', mock_open)
            async_file.__enter__()
            assert async_file.open.call_count == 1

    def test_exit(self, async_file, monkeypatch):
        mock_close = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(async_file, 'close', mock_close)
            async_file.__exit__(None, None, None)
            assert async_file.close.call_count == 1

    def test_exit_with_error(self, async_file, monkeypatch, caplog):
        mock_close = MagicMock()
        with caplog.at_level(logging.ERROR):
            with monkeypatch.context() as m:
                m.setattr(async_file, 'close', mock_close)
                async_file.__exit__(TypeError, 'some value', None)
                assert async_file.close.call_count == 1
                assert f'Got exception of type - "{TypeError}"' in caplog.text

    def test_open(self, async_file, monkeypatch):
        mock_open_file_location = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(async_file.file_location, 'open', mock_open_file_location)
            async_file.open()
            mock_open_file_location.assert_called_once_with('rb+')

    def test_open_repeat(self, monkeypatch, async_file):
        async_file._actual_file = 'something opened'
        mock_open_file_location = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(async_file.file_location, 'open', mock_open_file_location)
            async_file.open()
            mock_open_file_location.assert_not_called()

    def test_close(self, async_file):
        mock_close_file = MagicMock()
        async_file._actual_file = mock_close_file
        async_file.close()
        mock_close_file.close.assert_called_once()
        assert async_file._actual_file is None

    def test_close_failed(self, async_file, caplog):
        with caplog.at_level(logging.ERROR):
            async_file.close()
            assert "Tried closing file, that is not open" in caplog.text

    @pytest.mark.asyncio
    async def test_write_fail(self, async_file, caplog):
        with caplog.at_level(logging.ERROR):
            await async_file.write(b'x', 1)
            assert "Tried writing in closed file" in caplog.text

    @pytest.mark.asyncio
    async def test_write_success(self, async_file, monkeypatch):
        mock_file_seek = MagicMock()
        mock_file_write = MagicMock()
        async_file._actual_file = MagicMock()
        with monkeypatch.context() as m:
            m.setattr(async_file._actual_file, 'seek', mock_file_seek)
            m.setattr(async_file._actual_file, 'write', mock_file_write)
            await async_file.write(b'x', 1)
            mock_file_seek.assert_called_once_with(1)
            mock_file_write.assert_called_once_with(b'x')

    @pytest.mark.asyncio
    async def test_read_file_fail(self, async_file, caplog):
        with caplog.at_level(logging.ERROR):
            await async_file.read(1, 20)
            assert "Tried reading from closed file" in caplog.text

    @pytest.mark.asyncio
    async def test_read_file_success(self, async_file, monkeypatch):
        async_file._actual_file = MagicMock()
        async_file._actual_file.seek = MagicMock()
        async_file._actual_file.read = MagicMock(return_value=b"data")
        data = await async_file.read(10, 4)

        async_file._actual_file.seek.assert_called_once_with(10)
        async_file._actual_file.read.assert_called_once_with(4)
        assert data == b"data"

    def test_file_writer_enter_exit(self, file_writer, monkeypatch):
        with monkeypatch.context() as m:
            mock_file = MagicMock()
            mock_file.is_opened = True

            m.setattr(file_writer, '_prepare_file', MagicMock(return_value=mock_file))
            mock_torrent = MagicMock()
            mock_torrent.files = [
                {'path': ['folder', 'file1.txt'], 'length': 1024},
                {'path': ['folder', 'file2.txt'], 'length': 2048},
            ]

            with file_writer as fw:
                assert len(fw.files) == len(mock_torrent.files)
                assert file_writer._prepare_file.call_count == len(mock_torrent.files)

            with pytest.raises(ValueError):
                with file_writer:
                    raise ValueError("Test exception")

    @pytest.mark.asyncio
    async def test_write_segment(self, file_writer, monkeypatch):
        segment_id = 0
        data = b'test_data' * 2048

        mock_file = AsyncMock()
        file_writer.files = [mock_file]

        with monkeypatch.context() as m:
            m.setattr(file_writer, 'find_segment_in_files', MagicMock(return_value=[
                (mock_file, 0, 1024)
            ]))

            await file_writer.write_segment(segment_id, data)

            mock_file.write.assert_awaited_once_with(data[:1024], 0)

    @pytest.mark.asyncio
    async def test_read_segment(self, file_writer, monkeypatch):
        segment_id = 0

        mock_file = AsyncMock()
        mock_file.read.return_value = b'data'
        file_writer.files = [mock_file]

        with monkeypatch.context() as m:
            m.setattr(file_writer, 'find_segment_in_files', MagicMock(return_value=[
                (mock_file, 0, 1024)
            ]))

            result = await file_writer.read_segment(segment_id)
            mock_file.read.assert_awaited_once_with(0, 1024)
            assert result == b'data'

    @pytest.mark.asyncio
    async def test_check_segment_download(self, file_writer, monkeypatch):
        with monkeypatch.context() as m:
            m.setattr(file_writer, 'read_segment', AsyncMock(return_value=b'test_data'))
            m.setattr(hashlib, 'sha1',
                      MagicMock(return_value=MagicMock(digest=lambda: file_writer.torrent.segments_hash[0])))
            result = await file_writer.check_segment_download(0)

            assert result is True

    def test_shift_files_buffer(self, file_writer, monkeypatch):
        mock_file = MagicMock()
        file_writer.files_buffer = deque(maxlen=2)
        with monkeypatch.context() as m:
            m.setattr(mock_file, 'open', MagicMock())
            m.setattr(mock_file, 'close', MagicMock())
            file_writer.files_buffer.append(mock_file)

            new_file = MagicMock()

            file_writer._shift_files_buffer(new_file)

            new_file.open.assert_called_once()

    def test_prepare_file(self, file_writer, monkeypatch):
        file_path = MagicMock(spec=Path)
        file_length = 1024

        with monkeypatch.context() as m:
            m.setattr(file_writer, '_shift_files_buffer', MagicMock())
            m.setattr(Path, 'exists', MagicMock(return_value=False))
            m.setattr(Path, 'mkdir', MagicMock())
            m.setattr(file_path, 'stat', MagicMock())
            m.setattr(file_path, 'open', MagicMock())

            result = file_writer._prepare_file(file_path, file_length)
            assert result is not None

    def test_find_segment_in_files(self, file_writer, monkeypatch):
        segment_id = 0
        segment_length = file_writer.torrent.segment_length

        file_writer.file_pref_lengths = [0, 20480, 40960]
        mock_file_1 = MagicMock()
        mock_file_2 = MagicMock()
        file_writer.files = [mock_file_1, mock_file_2]

        with monkeypatch.context() as m:
            m.setattr(file_writer.torrent, 'segment_length', segment_length)
            result = list(file_writer.find_segment_in_files(segment_id))

            expected_start_in_file_1 = 0
            expected_size_in_file_1 = min(segment_length, 20480)
            assert len(result) > 0
            file, start_in_file, size_in_file = result[0]

            assert file == mock_file_1
            assert start_in_file == expected_start_in_file_1
            assert size_in_file == expected_size_in_file_1