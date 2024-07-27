import asyncio
import socket
import struct
import time
from asyncio import Queue

import aiohttp
import bencode


class TrackerEvent:
    STARTED = 'started'
    STOPPED = 'stopped'
    COMPLETED = 'completed'
    CHECK = ''


class TrackerClient:

    def __init__(self, url, info_hash, peer_id, port):
        self.http_client = aiohttp.ClientSession()
        self._peers = set()
        self.new_peers = Queue()

        self.url = url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.port = port

        self.request_interval = 60
        self.tracker_id = 0
        self.last_request_time = -1

    async def make_request(self, uploaded, downloaded, left, event):
        current_time = time.monotonic()
        time_diff = current_time - self.last_request_time
        if event != TrackerEvent.STARTED and time_diff < self.request_interval:
            if event:
                await asyncio.sleep(time_diff)
            else:
                return
        self.last_request_time = time.monotonic()

        params = {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id,
            'port': self.port,
            'compact': 0,
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
            self._parse_response(bencode.decode(data))

    def _parse_response(self, response):
        if 'failure' in response:
            raise ConnectionError(f'Unable to connect to "{self.url}: {response["failure"]}')

        self.request_interval = response.get(b'interval', self.request_interval)
        self.request_interval = response.get(b'min interval', self.request_interval)
        self.tracker_id = response.get(b'tracker id', self.tracker_id)

        peers = response[b'peers']
        peers = [self._decode_peer_data(peers[i:i + 6]) for i in range(0, len(peers), 6)]
        current_peers = set(peers)

        for peer in current_peers - self._peers:
            self.new_peers.put_nowait(peer)
        self._peers = current_peers

    def _decode_peer_data(self, row_data):
        ip = socket.inet_ntoa(row_data[:4])
        port = struct.unpack(">H", row_data[4:6])[0]
        return ip, port

    def close(self):
        self.http_client.close()
