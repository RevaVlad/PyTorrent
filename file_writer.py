import os
import logging, shutil
from pathlib import Path


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
            dir_path = file_path.parent

            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
            file = file_path.open('wb')
            self.files.append(file)

            pref_length += file_info['length']
            self.file_pref_lengths.append(pref_length)

            remaining_length = file_info['length']
            while remaining_length > 0:
                file.write(b'\x00' * min(remaining_length, self.BUFFER_LENGTH))
                remaining_length -= self.BUFFER_LENGTH

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for file in self.files:
            file.close()
        if exc_type is not None:
            logging.error(f'Got exception of type - "{exc_type}", with value - "{exc_val}" while writing files')

    def write(self, segment_id, data: bytes):
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
                writing_start = max(start_position, file_start)
                file.seek(writing_start - file_start)

                data_length = min(file_end, end_position) - writing_start
                file.write(data[:data_length])
                data = data[data_length:]
                if not data:
                    break


class FakeTorrent:
    files = [{'path': 'one.txt', 'length': 1},
             {'path': 'folder/2.txt', 'length': 6},
             {'path': 'folder/3.txt', 'length': 3}]
    segment_length = 2
    name = 'test'


if __name__ == '__main__':
    fake_torrent = FakeTorrent()

    with FileWriter(fake_torrent) as file_writer:
        file_writer.write(0, b'11')
        file_writer.write(2, b'22')
        file_writer.write(3, b'33')
        file_writer.write(1, b'44')
        file_writer.write(4, b'55')

    for dir_path, dir_names, filenames in os.walk('test'):
        for file in filenames:
            data = open(dir_path + '/' + file, 'rb').read()
            print(f"{file} - {data}, length - {len(data)}")

    # shutil.rmtree('test')
