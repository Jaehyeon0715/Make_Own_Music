# -*- coding: utf-8 -*-
"""Wake-on-LAN - send a magic packet to remotely power on the GPU PC."""
from __future__ import annotations

import socket


def _normalize_mac(mac: str) -> bytes:
    """'AA:BB:CC:DD:EE:FF' / 'AA-BB-...' / 'AABBCCDDEEFF' -> 6 bytes."""
    cleaned = mac.replace(":", "").replace("-", "").replace(".", "").strip()
    if len(cleaned) != 12:
        raise ValueError(f"Invalid MAC: {mac}")
    return bytes.fromhex(cleaned)


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Send a magic packet (0xFF*6 + MAC*16) as a broadcast.

    Note: WoL only works within the same LAN broadcast domain (not across routers).
    Wake-on-LAN must be enabled in the GPU PC BIOS/NIC.
    """
    payload = b"\xff" * 6 + _normalize_mac(mac) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(payload, (broadcast, port))
