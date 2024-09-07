import socket, asyncio, logging, upnpy
from peer_connection import PeerConnection
from upnpy import UPnP


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

        upnp = UPnP()

        devices = upnp.discover()

        if devices:

            device = devices[0]

            wan_ip_connection = device['WANIPConn1']

            if wan_ip_connection:
                external_port = 52656  # Порт на роутере
                internal_port = 52656  # Порт на компе
                internal_client = '192.168.1.108'
                protocol = 'TCP'
                description = 'Port Forwarding'

                try:
                    print(wan_ip_connection.get_actions())
                    # wan_ip_connection.DeletePortMapping(
                    #     NewRemoteHost='',
                    #     NewExternalPort=external_port,
                    #     NewProtocol=protocol
                    # )
                    # print("Deleted port mapping")
                    wan_ip_connection.AddPortMapping(
                        NewRemoteHost='',
                        NewExternalPort=external_port,
                        NewProtocol=protocol,
                        NewInternalPort=internal_port,
                        NewInternalClient=internal_client,
                        NewPortMappingDescription=description,
                        NewEnabled=False,
                        NewLeaseDuration=10000
                    )
                    print(f'Порт {external_port} успешно открыт на {internal_client}')
                except Exception as e:
                    print(f'Не удалось открыть порт: {e}')
            else:
                print('Снова нифига не получилось')
        else:
            print('Устройства с поддержкой UPnP не найдены')

        self.sock.bind(('192.168.1.108', 52656))

    @property
    def port(self):
        return self.sock.getsockname()[1]

    async def close(self):
        self.sock.close()
        await super().close()

    async def run_server(self):
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
