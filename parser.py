import hashlib
import logging

import bencode
from math import ceil


class TorrentData:

    def __init__(self, torrent_file_path):
        with open(torrent_file_path, 'rb') as f:
            raw_data = bencode.bdecode(f.read())

        self.trackers = self._get_announce_list(raw_data)
        info = raw_data['info']
        self.torrent_name = info['name']
        self.segment_length = info['piece length']
        self.segments_hash = [info['pieces'][i:i + 20] for i in range(0, len(info['pieces']), 20)]
        self.info_hash = hashlib.sha1(bencode.bencode(info)).digest()
        self.files = self._get_files_list(info)

        self.total_length = sum(file_info['length'] for file_info in self.files)
        # logging.info(f"Total length: {self.total_length}, in MB: {self.total_length / 2**20}. Piece length: {self.segment_length}")
        self.total_segments = ceil(self.total_length / self.segment_length)
        # logging.info(f'Total segments: {self.total_segments}')

    def _get_announce_list(self, data):
        return [url[0] for url in data['announce-list']] if 'announce-list' in data else [data['announce']]

    def _get_files_list(self, info):
        return info['files'] if 'files' in info else [{'length': info['length'], 'path': info['name']}]


if __name__ == '__main__':
    data = TorrentData('nobody.torrent')
    print(data.trackers, data.files, data.torrent_name, sep='\n')
