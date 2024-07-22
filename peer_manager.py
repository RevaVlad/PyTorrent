import hashlib
import bencode

import aiohttp


class TrackerClient:

    def __init__(self, url, info_hash, peer_id, port):
        self.http_client = aiohttp.ClientSession()
        self.peers = []

        self.url = url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.port = port

        self.request_interval = 0
        self.tracker_id = 0

    async def make_request(self, uploaded, downloaded, left, event):
        params = {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id,
            'port': self.port,
            'compact': 1,
            'uploaded': uploaded,
            'downloaded': downloaded,
            'left': left,
            'event': event
        }

        print(f'Making request at "{self.url}"')
        async with self.http_client.get(self.url, params=params) as response:
            if not response.status == 200:
                raise ConnectionError(f'Unable to connect to "{self.url}": status code {response.status}')
            data = await response.read()
            self.parse_response(bencode.bdecode(data))

    def parse_response(self, response):
        pass

    def get_peers(self):
        pass


class PeerManager:
    port = 6881

    def __init__(self, urls, info_hash):
        self.tracker_clients = []
        self.info_hash = info_hash
        self.peer_id = self.create_peer_id()

        for url in urls:
            self.add_tracker(url)

    def create_peer_id(self):
        return hashlib.sha1(self.info_hash)

    def add_tracker(self, url):
        self.tracker_clients.append(TrackerClient(url, self.info_hash, self.peer_id, self.port))
