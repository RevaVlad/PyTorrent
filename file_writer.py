import logging
import hashlib
import shutil
import random
from pathlib import Path
import asyncio
from collections import deque
import timeit


class AsyncFile:

    def __init__(self, file_location: Path):
        self.file_location = file_location
        self._actual_file = None
        self.lock = asyncio.Lock()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        if exc_type is not None:
            logging.error(
                f'Got exception of type - "{exc_type}", with value - "{exc_val}" while working with file {self.file_location.name}')

    def open(self):
        if self.is_opened:
            return
        self._actual_file = self.file_location.open('rb+')

    def close(self):
        if not self.is_opened:
            logging.error("Tried closing file, that is not open")
            return
        self._actual_file.close()
        self._actual_file = None

    async def write(self, data: bytes, position):
        if not self.is_opened:
            logging.error("Tried writing in closed file")
            return

        async with self.lock:
            self._actual_file.seek(position)
            self._actual_file.write(data)

    async def read(self, position, size):
        if not self.is_opened:
            logging.error("Tried reading from closed file")
            return

        async with self.lock:
            self._actual_file.seek(position)
            data = self._actual_file.read(size)
        return data

    @property
    def is_opened(self):
        return self._actual_file is not None


class FileWriter:
    WRITE_BUFFER_LENGTH = 2 ** 13
    FILES_BUFFER_LENGTH = 10

    def __init__(self, torrent, destination: Path):
        self.destination = destination
        self.torrent = torrent

        self.segment_length = torrent.segment_length
        self.file_pref_lengths = [0]
        self.files = []
        self.files_buffer = deque(maxlen=FileWriter.FILES_BUFFER_LENGTH)

    def __enter__(self):
        common_path = self.destination / self.torrent.torrent_name if len(self.torrent.files) != 1 else self.destination
        pref_length = 0
        for file_info in self.torrent.files:
            file_path = common_path / Path.joinpath(*[Path(path_piece) for path_piece in file_info['path']])
            self.files.append(self._prepare_file(file_path, file_info['length']))
            pref_length += file_info['length']
            self.file_pref_lengths.append(pref_length)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for file in self.files_buffer:
            if file.is_opened:
                file.close()

        if exc_type is not None:
            logging.error(f'Got exception of type - "{exc_type}", with value - "{exc_val}" while writing files')

    def _prepare_file(self, file_path: Path, file_length):
        directory_path = file_path.parent

        if not directory_path.exists():
            directory_path.mkdir(parents=True, exist_ok=True)
        if file_path.exists() and file_path.stat().st_size == file_length:
            return AsyncFile(file_path)
        file_path.open('w').close()

        with file_path.open('rb+') as file:
            remaining_length = file_length
            while remaining_length > 0:
                file.write(b'\x00' * min(remaining_length, self.WRITE_BUFFER_LENGTH))
                remaining_length -= self.WRITE_BUFFER_LENGTH

        return AsyncFile(file_path)

    def find_segment_in_files(self, segment_id):
        segment_length = self.torrent.segment_length

        start_position = segment_id * segment_length
        end_position = start_position + segment_length

        for file_id in range(len(self.files)):
            file_start = self.file_pref_lengths[file_id]
            file_end = self.file_pref_lengths[file_id + 1]

            if (start_position <= file_start <= end_position or
                    start_position <= file_end <= end_position or
                    file_start <= start_position <= end_position <= file_end):
                file = self.files[file_id]
                segment_start_in_file = max(start_position, file_start) - file_start
                segment_size_in_file = min(file_end, end_position) - segment_start_in_file - file_start
                yield file, segment_start_in_file, segment_size_in_file

    async def write_segment(self, segment_id, data: bytes):
        for file, writing_start, size in self.find_segment_in_files(segment_id):
            self._shift_files_buffer(file)
            await file.write(data[:size], writing_start)
            data = data[size:]
            if not data:
                break

    async def read_segment(self, segment_id):
        result = b''
        for file, reading_start, size in self.find_segment_in_files(segment_id):
            self._shift_files_buffer(file)
            result += await file.read(reading_start, size)
            if len(result) == self.torrent.segment_length:
                break
        return result

    async def check_segment_download(self, index: int) -> bool:
        data = await self.read_segment(index)
        if hashlib.sha1(data).digest() != self.torrent.segments_hash[index]:
            return False
        return True

    def _shift_files_buffer(self, new_file):
        if new_file in self.files_buffer:
            return
        new_file.open()
        if len(self.files_buffer) >= FileWriter.FILES_BUFFER_LENGTH:
            old_file = self.files_buffer.pop()
            if old_file not in self.files_buffer:
                old_file.close()
        self.files_buffer.append(new_file)


class FakeTorrent:
    files = [{'path': ['one.txt'], 'length': 2},
             {'path': ['folder/two.txt'], 'length': 1},
             {'path': ['folder/three.txt'], 'length': 6}]
    segment_length = 3
    torrent_name = 'basic'


class FakeTorrentManyFiles:
    files = [{'path': [f'{i:04d}.txt'], 'length': 2} for i in range(10_000)]
    segment_length = 5
    torrent_name = '10k_files'


'''
if __name__ == '__main__':
    async def basic():
        fake_torrent = FakeTorrent()

        with FileWriter(fake_torrent, Path('./downloaded')) as file_writer:
            await asyncio.gather(file_writer.write_segment(0, b'111'),
                                 file_writer.write_segment(1, b'222'),
                                 file_writer.write_segment(2, b'333'))

            results = await asyncio.gather(file_writer.read_segment(0),
                                           file_writer.read_segment(1),
                                           file_writer.read_segment(2))

        for dir_path, dir_names, filenames in os.walk('./downloaded/' + fake_torrent.torrent_name):
            for file in filenames:
                data = open(dir_path + '/' + file, 'rb').read()
                print(f"{file} - {data}, length - {len(data)}")

        shutil.rmtree('./downloaded/' + fake_torrent.torrent_name)
    

    async def many_files():
        torrent = FakeTorrentManyFiles()

        with FileWriter(torrent, Path('./downloaded')) as fw:
            requests = [fw.write_segment(segment_id, bytes(str(segment_id)[0] * torrent.segment_length, encoding='utf-8'))
                        for segment_id in range(4000)]
            random.shuffle(requests)
            await asyncio.gather(*requests)
        with FileWriter(torrent, Path('./downloaded')) as fw:
            for segment_id in range(4000):
                data = await fw.read_segment(segment_id)
                assert data == bytes(str(segment_id)[0] * torrent.segment_length, encoding='utf-8')

        shutil.rmtree('./downloaded/' + torrent.torrent_name)

    print(timeit.timeit(lambda: asyncio.run(many_files()), number=1))
    '''
