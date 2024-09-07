import asyncio
import logging
import socket
from pubsub import pub
import bitstring

from peer_connection import PeerConnection


class PeerReceiver(PeerConnection):

    def __init__(self, sock, address):
        PeerConnection.__init__(self, address[0], 0, '', address[1])
        self.sock = sock
        self.already_connected = False

        self.run_task = None

    async def get_info_hash(self):
        if not await self.connect():
            self.is_active = False

        self.run_task = asyncio.create_task(self.run())
        pub.subscribe(self._get_handshake, self.got_handshake_event)
        for _ in range(1000):
            await asyncio.sleep(.01)
            if self.info_hash:
                break
        else:
            self.run_task.cancel()
        logging.info(f'Got info hash: {self.info_hash}')
        pub.unsubscribe(self._get_handshake, self.got_handshake_event)

        return self.info_hash

    def _get_handshake(self, handshake_message):
        logging.info("Got handshake message")
        self.info_hash = handshake_message.info_hash
        logging.info("wrote info hash")

    def initiate_bitfield(self, number_of_pieces):
        bitfield_length = number_of_pieces if number_of_pieces % 8 == 0 else number_of_pieces + 8 - number_of_pieces % 8
        self.bitfield = bitstring.BitArray(bitfield_length)

    def close(self):
        if self.run_task:
            self.run_task.cancel()
        PeerConnection.close(self)

    async def connect(self) -> bool:
        if self.already_connected:
            return True

        try:
            self.reader, self.writer = await asyncio.open_connection(sock=self.sock)
            self.is_active = True
        except (asyncio.TimeoutError, OSError):
            logging.error(f'Socket error: Пир {self.ip}:{self.port} не может быть подключён')
            return False
        logging.info("chebureck connected")
        return True


class RequestsReceiver:
    NEW_PEER_EVENT = 'newPeerReceived'
    ACCEPT_TIMEOUT = 100

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.available_peers = asyncio.Queue()
        self.sock.bind(('', 52656))

        self._task = None

    @property
    def port(self):
        return self.sock.getsockname()[1]

    async def close(self):
        self.sock.close()
        self._task.cancel()

    def start_server(self):
        self._task = asyncio.create_task(self._run_server())

    async def _run_server(self):
        self.sock.listen(1)
        self.sock.setblocking(False)

        loop = asyncio.get_event_loop()
        while True:
            while True:
                try:
                    client_sock, client_addr = await asyncio.wait_for(loop.sock_accept(self.sock),
                                                                      timeout=RequestsReceiver.ACCEPT_TIMEOUT)
                    await self.add_peer(client_sock, client_addr)
                    await self.available_peers.put((client_sock, client_addr))
                except asyncio.TimeoutError:
                    logging.info("Timeout")

    async def add_peer(self, sock, address):
        peer = PeerReceiver(sock, address)
        info_hash = await peer.get_info_hash()
        if not info_hash:
            return

        # pub.sendMessage(self.NEW_PEER_EVENT, peer, info_hash)
