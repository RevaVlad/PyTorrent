import hashlib
import bencode

class TorrentData:

    def __init__(self, torrent_file_path):
        with open(torrent_file_path, 'rb') as f:
            data = bencode.bdecode(f.read())

        self.trackers = self.get_announce_list(data)
        info = data['info']
        self.torrent_name = info['name']
        self.segment_length = info['piece length']
        self.pieces_hash = [info['pieces'][i:i + 20] for i in range(0, len(info['pieces']), 20)]
        self.info_hash = hashlib.sha1(bencode.bencode(info)).digest()
        self.files = self.get_files_list(info)

    def get_announce_list(self, data):
        return [url[0] for url in data['announce-list']] if 'announce-list' in data else [data['announce']]

    def get_files_list(self, info):
        return info['files'] if 'files' in info else [{'length': info['length'], 'path': self.torrent_name}]


if __name__ == '__main__':
    TorrentData("nobody.torrent")
