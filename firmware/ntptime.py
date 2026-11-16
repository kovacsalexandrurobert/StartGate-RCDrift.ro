"""UTC bootstrap for certificate validation. No timezone or credentials.
Protocol reference: micropython-lib/micropython/net/ntptime/ntptime.py.
"""
import socket
import struct
import time as clock
host = "pool.ntp.org"
timeout = 1


def settime():
    query = bytearray(48)
    query[0] = 0x23
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.settimeout(timeout)
        address = socket.getaddrinfo(host, 123)[0][-1]
        connection.sendto(query, address)
        response = connection.recv(48)
    finally:
        connection.close()
    if len(response) < 48 or not 0 < response[1] < 16 or response[0] & 7 != 4:
        raise OSError("Invalid NTP response")
    seconds = struct.unpack("!I", response[40:44])[0]
    if not seconds:
        raise OSError("Missing NTP timestamp")
    if seconds < 3913056000:
        seconds += 0x100000000
    epoch = clock.gmtime(0)[0]
    if epoch not in (1970, 2000):
        raise OSError("Unsupported epoch")
    utc = clock.gmtime(seconds - (2208988800 if epoch == 1970 else 3155673600))
    import machine
    machine.RTC().datetime((utc[0], utc[1], utc[2], utc[6]+1, utc[3], utc[4], utc[5], 0))
