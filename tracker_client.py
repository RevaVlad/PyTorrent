import asyncio
import re
import socket
import struct
import time
import logging
import os
from asyncio import Queue
from enum import Enum
from urllib.parse import urlencode

import aiohttp
import bencode


class TrackerEvent(Enum):
    STARTED = 'started'
    STOPPED = 'stopped'
    COMPLETED = 'completed'
    CHECK = ''


class HttpTrackerClient:

    def __init__(self, url, info_hash, peer_id, port, segment_info):
        self._peers = set()
        self.new_peers = Queue()

        self.url = url
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.port = port
        self.segment_info = segment_info

        self.request_interval = 60
        self.tracker_id = 0
        self.last_request_time = -1

    async def make_request(self, event):
        current_time = time.monotonic()
        time_diff = current_time - self.last_request_time
        if event and time_diff < self.request_interval:
            await asyncio.sleep(time_diff)
        self.last_request_time = time.monotonic()

        params = {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id,
            'port': self.port,
            'compact': 1,
            'uploaded': self.segment_info.uploaded,
            'downloaded': self.segment_info.downloaded,
            'left': self.segment_info.left,
            'event': event.value
        }

        if event != TrackerEvent.CHECK:
            logging.info(f'Making request at "{self.url}" with params: {params}')

        async with aiohttp.ClientSession() as http_client:
            async with http_client.get(self.url + '?' + urlencode(params), timeout=10) as response:
                if not response.status == 200:
                    raise ConnectionError(f'Unable to connect to "{self.url}": status code {response.status}')
                data = await response.read()
                self._parse_response(bencode.decode(data))
                return

    def _parse_response(self, response):
        if 'failure reason' in response:
            raise ConnectionError(f'Unable to connect to "{self.url}: {response["failure reason"]}')

        self.request_interval = response.get('interval', self.request_interval)
        self.request_interval = response.get('min interval', self.request_interval)
        self.tracker_id = response.get('tracker id', self.tracker_id)

        peers = response['peers']
        if type(peers) == list:
            peers = [(peer_data['ip'], peer_data['port']) for peer_data in peers]
        else:
            peers = [self._decode_peer_data(peers[i:i + 6]) for i in range(0, len(peers), 6)]
        current_peers = set(peers)

        for peer in current_peers - self._peers:
            self.new_peers.put_nowait(peer)
        self._peers = current_peers

    def _decode_peer_data(self, row_data):
        ip = socket.inet_ntoa(row_data[:4])
        port = struct.unpack(">H", row_data[4:6])[0]
        return ip, port

    async def close(self):
        try:
            await self.make_request(TrackerEvent.STOPPED)
        except asyncio.TimeoutError:
            logging.error('Timeout error while close connection with tracker')


class LocalConnections:

    regular_exp = re.compile(r'IPv4.*[0-9]+(?:\.[0-9]+){3}')
    ip_exp = re.compile(r'[0-9]+(?:\.[0-9]+){2}')

    def __init__(self):
        self._peers = set()
        self.new_peers = asyncio.Queue()

        self.ip_start = self.ip_exp.findall(self.regular_exp.search(os.popen('ipconfig').read()).group())[0]

    async def make_request(self, _):
        for i in range(200):
            await self._add_peer(self.ip_start + '.' + str(i))

    async def _add_peer(self, peer_ip):
        if peer_ip in self._peers:
            return
        await self.new_peers.put((peer_ip, 52656))

    async def close(self):
        pass
