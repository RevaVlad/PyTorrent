import pytest
import asyncio
import shutil
import os
from file_writer import FileWriter


@pytest.fixture
def fake_torrent():
    class FakeTorrent:
        files = [{'path': 'one.txt', 'length': 1},
                 {'path': 'folder/two.txt', 'length': 2},
                 {'path': 'folder/three.txt', 'length': 6}]
        segment_length = 3
        name = 'test_folder'

        _segments_data = [b'111', b'222', b'333']
        _expected_data = {'one.txt': b'1', 'three.txt': b'222333', 'two.txt': b'11'}

    return FakeTorrent()


class TestFileWriter:
    def test_files_data(self, fake_torrent):
        async def write_segments():
            with FileWriter(fake_torrent) as file_writer:
                await asyncio.gather(file_writer.write_segment(0, b'111'),
                                     file_writer.write_segment(1, b'222'),
                                     file_writer.write_segment(2, b'333'))

                results = await asyncio.gather(file_writer.read_segment(0),
                                               file_writer.read_segment(1),
                                               file_writer.read_segment(2))
            return results

        try:
            results = asyncio.run(write_segments())
            assert results == fake_torrent._segments_data

            for dir_path, dir_names, filenames in os.walk(fake_torrent.name):
                for file in filenames:
                    data = open(dir_path + '/' + file, 'rb').read()
                    assert data == fake_torrent._expected_data[file]
        finally:
            shutil.rmtree(fake_torrent.name)
