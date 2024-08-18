import logging
import select
import socket
from threading import Thread
from peer_manager import PeerManager


class PeerInteraction(Thread):
    def __init__(self, torrent):
        super().__init__()
        self.peers = []
        self.torrent = torrent
        self.is_active = True
        self.peer_manager = PeerManager(self.torrent)

    def add_peer(self, peers):
        for peer in peers:
            if self.peer_manager.peer_handshake(peer):
                self.peers.append(peer)
            else:
                print('Возникли проблемы с установлением соединения с пиром')

    def remove_peer(self, peer):
        if peer in self.peers:
            try:
                peer.socket.close()
            except socket.error:
                logging.exception('Произошла проблема с закрытием соединения')

        self.peers.remove(peer)

        for i in range(len(self.peer_manager.available_pieces)):
            if peer in self.peer_manager.available_pieces[i][1]:
                self.peer_manager.available_pieces[i][1].remove(peer)
                self.peer_manager.available_pieces[i][0] -= 1

    def get_peer_from_socket(self, sock):
        for peer in self.peers:
            if peer.socket == sock:
                return peer

        logging.error('Пира с таким сокетом нет')
        return None

    def run(self):
        while self.is_active:
            sockets = [peer.socket for peer in self.peers]
            list_for_read = select.select(sockets, [], [], 1)

            for sock in list_for_read:
                peer = self.get_peer_from_socket(sock)
                if peer.is_active is False:
                    self.remove_peer(peer)
                    continue

                read_data = self.peer_manager.read_socket(sock)
                peer.buffer += read_data

                for message in peer.get_message():
                    self.peer_manager.get_new_message(message, peer)

