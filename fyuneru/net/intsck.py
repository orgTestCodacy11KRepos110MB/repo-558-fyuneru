# -*- coding: utf-8 -*-

"""
Internal Fyuneru Socket for Proxy Processes

A fyuneru socket basing on UDP socket is defined. It is always a listening UDP
socket on a port in local addr, which does automatic handshake with given
internal magic word, and provides additionally abilities like encryption
underlays, traffic statistics, etc.
"""

import os
import sys
from logging import debug, info, warning, error
from time import time
from struct import pack, unpack
from socket import socket, AF_INET, SOCK_DGRAM
import random
from ..util.crypto import Crypto

UDPCONNECTOR_WORD = \
    "Across the Great Wall, we can reach every corner in the world."

IPCPort = 64089

##############################################################################

class InternalSocketServer:

    __sockpath = None
    __sock = None

    peers = {}

    sendtiming = 0
    recvtiming = 0

    def __init__(self, key):
        self.__crypto = Crypto(key)
        self.__sock = socket(AF_INET, SOCK_DGRAM)
        self.__sock.bind(("127.0.0.1", IPCPort))

    def __getattr__(self, name):
        return getattr(self.__sock, name)

    def __registerPeer(self, addrTuple):
        self.peers[addrTuple] = True

    def close(self):
        # close socket
        debug("Internal socket shutting down...")
        try:
            self.__sock.close()
        except Exception,e:
            error("Error closing socket: %s" % e)

    def clean(self):
        # reserved for doing clean up jobs relating to the peer delays
        pass

    def receive(self):
        buf, sender = self.__sock.recvfrom(65536)

        if buf.strip() == UDPCONNECTOR_WORD:
            # connection word received, answer
            self.__registerPeer(sender)
            self.__sock.sendto(UDPCONNECTOR_WORD, sender)
            return None

        decryption = self.__crypto.decrypt(buf)
        if not decryption: return None

        if len(decryption) < 8: return None
        header = decryption[:8]
        timestamp = unpack('<d', header)[0]
        buf = decryption[8:]

        self.recvtiming = max(self.recvtiming, timestamp)
        self.__registerPeer(sender)
        return buf 

    def send(self, buf):
        # choose a peer randomly
        possiblePeers = [i for i in self.peers if self.peers[i]]
        if len(possiblePeers) < 1: return
        peer = possiblePeers[random.randrange(0, len(possiblePeers))]
        # send to this peer
        self.sendtiming = time()
        header = pack('<d', self.sendtiming)
        encryption = self.__crypto.encrypt(header + buf)
        try:
            # reply using last recorded peer
            self.__sock.sendto(encryption, peer)
        except Exception,e:
            error(e) # for debug
            self.peers[peer] = False # this peer may not work


class InternalSocketClient:

    __sock = None
    __peer = ("127.0.0.1", IPCPort) 
    
    connected = False
    __lastbeat = 0

    def __init__(self, name):
        self.__name = name
        self.__sock = socket(AF_INET, SOCK_DGRAM)

    def __getattr__(self, name):
        return getattr(self.__sock, name)

    def close(self):
        debug("Internal socket shutting down...")
        try:
            self.__sock.close()
        except Exception,e:
            error("Error closing socket: %s" % e)

    def heartbeat(self):
        if not self.connected or time() - self.__lastbeat > 5:
            try:
                self.__lastbeat = time()
                self.__sock.sendto(UDPCONNECTOR_WORD, self.__peer)
            except Exception,e:
                self.connected = False
                print e

    def receive(self):
        buf, sender = self.__sock.recvfrom(65536)
        if sender != self.__peer: return None
        if buf.strip() == UDPCONNECTOR_WORD:
            # connection word received, answer
            debug("CONNECTION: %s(IPCCli)" % self.__name)
            self.connected = True
            return None
        return buf 

    def send(self, buf):
        if not self.connected: return
        try:
            # reply using last recorded peer
            self.__sock.sendto(buf, self.__peer)
        except Exception,e:
            print e # for debug
            self.connected = False # this peer may not work
