#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
from select import select
import signal
import logging
from logging import info, debug, warning, error, critical

from fyuneru.net.vnet import VirtualNetworkInterface
from fyuneru.util.crypto import randint
from fyuneru.util.debug import showPacket
from fyuneru.util.droproot import dropRoot
from fyuneru.net.protocol import DataPacket, DataPacketException
from fyuneru.net.intsck import InternalSocketServer
from fyuneru.util.procmgr import ParentProcessWatcher

##############################################################################

parser = argparse.ArgumentParser()
parser.add_argument(\
    "--debug",
    action="store_true",
    default=False
)
parser.add_argument(\
    "--uidname",
    metavar="UID_NAME",
    type=str,
    required=True
)
parser.add_argument(\
    "--gidname",
    metavar="GID_NAME",
    type=str,
    required=True
)
parser.add_argument(\
    "--parent-pid",
    type=int,
    required=True
)
parser.add_argument(\
    "--role",
    metavar="ROLE",
    type=str,
    choices=["server", "client"],
    default="s",
    required=True
)
parser.add_argument(\
    "--server-ip",
    metavar="SERVER_IP",
    type=str,
    required=True
)
parser.add_argument(\
    "--client-ip",
    metavar="CLIENT_IP",
    type=str,
    required=True
)
parser.add_argument(\
    "--key",
    metavar="KEY",
    type=str,
    required=True
)
parser.add_argument(\
    "SOCKET_NAME",
    type=str,
    nargs="+"
)

args = parser.parse_args()


MTU = 1400 
UDPCONNECTOR_WORD = \
    "Across the Great Wall, we can reach every corner in the world."
UNIX_SOCKET_NAMES = args.SOCKET_NAME

##############################################################################

# ---------- config log/debug functions

if args.debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

# ---------- config TUN device

if "client" == args.role:
    info("Running as client.")
    tun = VirtualNetworkInterface(args.client_ip, args.server_ip)
else:
    info("Running as server.")
    tun = VirtualNetworkInterface(args.server_ip, args.client_ip)
tun.netmask = "255.255.255.0"
tun.mtu = MTU

info(\
    """%s: mtu %d  addr %s  netmask %s  dstaddr %s""" % \
    (tun.name, tun.mtu, tun.addr, tun.netmask, tun.dstaddr)
)

tun.up()
info("%s: up now." % tun.name)

# ---------- create IPC server

ipc = InternalSocketServer(args.key)

# ---------- drop root privileges

uidname, gidname = args.uidname, args.gidname
dropRoot(uidname, gidname)

# ---------- loop

reads = [ipc, tun] # for `select` function

##############################################################################

def doExit(signum, frame):
    global reads 
    info("Exit now.")
    for each in reads:
        each.close()
    exit()
signal.signal(signal.SIGTERM, doExit)

parentProc = ParentProcessWatcher(args.parent_pid, doExit)



while True:
    try:
        parentProc.watch()
        
        # ---------- deal with I/O things
        
        readables = select(reads, [], [], 0.5)[0]
        for each in readables:
            if each == tun:
                # ---------- forward packets came from tun0
                buf = each.read(65536) # each.read(each.mtu)
                # pack buf with timestamp
                packet = DataPacket()
                packet.data = buf
                # encrypt and sign buf
                ipc.send(str(packet))
                debug(showPacket(buf))
            if each == ipc:
                # ---------- receive packets from internet
                buf = each.receive()
                if buf == None:
                    # Received buffer being digested by InternalSocket itself,
                    # either some internal mechanism packet, or packet with
                    # wrong destination, or packet decryption failed...
                    continue

                try:
                    packet = DataPacket(buf)
                except DataPacketException, e:
                    # if failed reading the packet
                    debug("[%d] --> %s: Bad packet - %s" % (i, tun.name, e))
                    continue
                
                # send buf to network interface
                tun.write(packet.data)
                debug(showPacket(packet.data))

        # ---------- deal with tunnel delay timings

        ipc.clean()


    except KeyboardInterrupt:
        doExit(None, None)
