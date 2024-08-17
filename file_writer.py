import logging
import os
import shutil
from pathlib import Path
import asyncio


class AsyncFile:

    def __init__(self, actual_file):
        self.actual_file = actual_file
        self.lock = asyncio.Lock()

    def close(self):
        self.actual_file.close()

    async def write(self, data: bytes, position):
        async with self.lock:
            self.actual_file.seek(position)
            self.actual_file.write(data)

    async def read(self, position, size):
        async with self.lock:
            self.actual_file.seek(position)
            data = self.actual_file.read(size)
        return data


class FileWriter:
    BUFFER_LENGTH = 2 ** 13

    def __init__(self, torrent):
        self.segment_length = torrent.segment_length
        self.file_pref_lengths = [0]
        self.files = []
        self.torrent = torrent

    def __enter__(self):
        common_path = Path('.') if len(self.torrent.files) == 1 else Path('.') / self.torrent.name
        pref_length = 0
        for file_info in self.torrent.files:
            file_path = common_path / file_info['path']
            self.files.append(self._prepare_file(file_path, file_info['length']))
            pref_length += file_info['length']
            self.file_pref_lengths.append(pref_length)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for file in self.files:
            file.close()
        if exc_type is not None:
            logging.error(f'Got exception of type - "{exc_type}", with value - "{exc_val}" while writing files')

    def _prepare_file(self, file_path, file_length):
        directory_path = file_path.parent

        if not directory_path.exists():
            directory_path.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.open('w').close()
        file = file_path.open('rb+')

        remaining_length = file_length
        while remaining_length > 0:
            file.write(b'\x00' * min(remaining_length, self.BUFFER_LENGTH))
            remaining_length -= self.BUFFER_LENGTH

        return AsyncFile(file)

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
            await file.write(data[:size], writing_start)
            data = data[size:]
            if not data:
                break

    async def read_segment(self, segment_id):
        result = b''
        for file, reading_start, size in self.find_segment_in_files(segment_id):
            result += await file.read(reading_start, size)
            if len(result) == self.torrent.segment_length:
                break
        return result




if __name__ == '__main__':
    pass