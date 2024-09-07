import socket, asyncio, logging, upnpy
from peer_connection import PeerConnection


class PeerReceiver(PeerConnection):

    def __init__(self, socket, client_address, number_of_pieces: int, info_hash):
        self.sock = socket
        super().__init__(client_address[0], number_of_pieces, info_hash, client_address[1])

    async def connect(self) -> bool:
        try:
            self.reader, self.writer = await asyncio.open_connection(sock=self.sock)
            self.is_active = True
        except (asyncio.TimeoutError, OSError):
            logging.error(f'Socket error: Пир {self.ip}:{self.port} не может быть подключён')
            return False
        logging.info("Chebureck connected")
        return True


class RequestsReceiver:
    ACCEPT_TIMEOUT = 100

    def __init__(self, torrent_data):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.available_peers = asyncio.Queue()
        self.torrent = torrent_data
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
                    logging.info(f"New chebureck: {client_addr}")
                    await self.available_peers.put(PeerReceiver(client_sock,
                                                                client_addr,
                                                                self.torrent.total_segments,
                                                                self.torrent.info_hash))
                except asyncio.TimeoutError:
                    logging.info("Timeout")
