import asyncio
import errno
import ipaddress
import socket
import struct
import time
import logging
import urllib.parse
import Message
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


class TrackerClient:

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
        if self.url.startswith('http'):
            await self.make_request_http(event)
        else:
            await self.make_request_udp(event)

    async def make_request_http(self, event):
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
            'compact': 1,
            'uploaded': self.segment_info.uploaded,
            'downloaded': self.segment_info.downloaded,
            'left': self.segment_info.left,
            'event': event.value
        }

        if event != TrackerEvent.CHECK:
            logging.info(f'Making request at "{self.url}" with params: {params}')
        while True:
            try:
                async with aiohttp.ClientSession() as http_client:
                    async with http_client.get(self.url + '?' + urlencode(params), timeout=10) as response:
                        if not response.status == 200:
                            raise ConnectionError(f'Unable to connect to "{self.url}": status code {response.status}')
                        data = await response.read()
                        self._parse_response(bencode.decode(data))
                        return
            except (aiohttp.ClientError, asyncio.TimeoutError):
                logging.info('Неудачная попытка входа')
                await asyncio.sleep(10)

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

    async def make_request_udp(self, event):
        events = {
            TrackerEvent.STARTED: 2,
            TrackerEvent.STOPPED: 3,
            TrackerEvent.COMPLETED: 1,
            TrackerEvent.CHECK: 0
        }

        parsed_url = urllib.parse.urlparse(self.url)
        loop = asyncio.get_running_loop()

        try:
            addr_info = await loop.getaddrinfo(parsed_url.hostname, parsed_url.port, family=socket.AF_INET,
                                               type=socket.SOCK_DGRAM)
            ip, port = addr_info[0][4]
        except Exception as e:
            logging.error(f"Error resolving address: {e}")
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(10)
        sock.setblocking(False)

        if ipaddress.ip_address(ip).is_private:
            logging.info(f'private ip {ip}')
            return

        logging.info(f"Sending UDP connection request to {ip}:{port}")
        response = await self.send_message((ip, port), loop, sock, Message.UDPConnectionMessage())

        if not response:
            logging.error("No response from UdpTrackerConnection")
            return

        logging.debug("Received response from UDP tracker")
        tracker_connection_output = Message.UDPConnectionMessage()
        tracker_connection_output.decode(response)

        tracker_announce_input = Message.UPDTrackerAnnounceInput(self.info_hash,
                                                                 tracker_connection_output.connection_id,
                                                                 self.peer_id, events[event])
        response = await self.send_message((ip, port), loop, sock, tracker_announce_input)

        if not response:
            logging.error("No response from UdpTrackerAnnounce")
            return

        tracker_announce_output = Message.UPDTrackerAnnounceOutput()
        tracker_announce_output.decode(response)

        peers = [(ip, port) for ip, port in tracker_announce_output.list_peers]
        current_peers = set(peers)
        for peer in current_peers - self._peers:
            self.new_peers.put_nowait(peer)
        self._peers = current_peers

    async def send_message(self, conn, loop, sock, tracker_message):
        message = tracker_message.encode()
        logging.debug(f"Sending message: {message.hex()} to {conn}")

        sock.sendto(message, conn)

        try:
            response = await self._read_from_socket_udp(loop, sock)
        except asyncio.TimeoutError as e:
            logging.error(f"Timeout when sending message {message.hex()}: {e}")
            return
        except socket.error as e:
            logging.error(f"Error when sending message: {e}")
            return

        logging.debug(f"Received response: {response.hex()}")
        return response

    async def _read_from_socket_udp(self, loop, sock):
        data = b''

        while True:
            try:
                buff = await asyncio.wait_for(loop.sock_recv(sock, 4096), timeout=60)
                if len(buff) <= 0:
                    break
                data += buff
            except asyncio.TimeoutError as e:
                logging.error(f"Timeout while waiting for data {e}")
                break
            except socket.error as e:
                logging.error(f"Socket error: {e}")
                break

        return data

    async def close(self):
        try:
            await self.make_request(TrackerEvent.STOPPED)
        except asyncio.TimeoutError:
            pass
