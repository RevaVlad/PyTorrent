import asyncio
import logging
import socket
from pubsub import pub
import bitstring
import Message

from peer_connection import PeerConnection
from struct import unpack


class PeerReceiver(PeerConnection):
    GOT_HANDSHAKE_EVENT = 'gotHandshakeMessage'  # + ip, args: handshakeMessage

    def __init__(self, sock, address):
        PeerConnection.__init__(self, address[0], 0, '', address[1])
        self.sock = sock
        logging.info(address)
        self.got_handshake_event = PeerReceiver.GOT_HANDSHAKE_EVENT + address[0]

        self.already_connected = False
        self.already_sent_handshake = False
        self.run_task = None

    async def handle_handshake(self):
        if not self.already_sent_handshake:
            self.already_sent_handshake = True
            return await PeerConnection.handle_handshake(self)
        return True

    def handle_handshake_for_buffer(self) -> bool:
        if len(self.buffer) >= 68 and unpack('!B', self.buffer[:1])[0] == 19:
            logging.info("Got handshake!")
            handshake_message = Message.HandshakeMessage.decode(self.buffer[:68])
            pub.sendMessage(topicName=self.got_handshake_event, handshake_message=handshake_message)
            logging.info('Sent event')
            self.handshake = True
            self.buffer = self.buffer[68:]
            return True
        return False

    async def get_info_hash(self):
        await self.connect()

        self.run_task = asyncio.create_task(self.run())
        pub.subscribe(self._get_handshake, self.got_handshake_event)
        for _ in range(1000):
            await asyncio.sleep(.01)
            if self.info_hash:
                break
        else:
            self.run_task.cancel()
        logging.info(f'Got info hash: {self.info_hash}')
        # pub.unsubscribe(self._get_handshake, self.got_handshake_event)

        return self.info_hash

    def _get_handshake(self, handshake_message):
        self.info_hash = handshake_message.info_hash

    async def initiate_bitfield(self, number_of_pieces, our_bitfield: bitstring.BitArray):
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
        self.already_connected = True
        logging.info("chebureck connected")
        return True


class RequestsReceiver:
    NEW_PEER_EVENT = 'newPeerReceived1213u213'
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

        pub.sendMessage(topicName=RequestsReceiver.NEW_PEER_EVENT, peer=peer, info_hash=info_hash)
