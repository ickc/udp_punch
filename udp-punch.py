#!/usr/bin/env python3

"""
This is a 100% self-contained script to facilitate automated creation of bidirectional UDP pinholes.
It should work as a non-root user assuming you use a high port number. 
All that is necessary is an SSH server with a Python environment.
This script is ran on the client, and then the client runs it on the server dynamically. 
No permanent changes are made to the server.

Basically we just open UDP connection from both ends, to the same port, and then exchange some tokens to verify connectivity.

Output is pretty verbose, showing the negotiation from both ends.
The server's output will be returned after negotiation.

To facilitate negotiation, a random token is generated on each end, and then they are cross checked.

Yes, this works if you have firewall/NAT on both ends!

The idea here is to use this for MOSH, to open UDP ports dynamically on demand.

~ » ~/Bin/udp-punch user@xxxxxx.com 60001
Wed Oct  4 06:39:16 2017 Attempitng to punch to host: xxxxxx.com on port: 60001
Wed Oct  4 06:39:16 2017 Binding local socket
Wed Oct  4 06:39:16 2017 Generated random token: 0.11894490465224017
Wed Oct  4 06:39:16 2017 Attempitng to start reverse punch on remote...
Wed Oct  4 06:39:16 2017 ====== Attempt #0
Wed Oct  4 06:39:16 2017 Sent: b'0.11894490465224017 NULL'
Wed Oct  4 06:39:17 2017 ====== Attempt #1
Wed Oct  4 06:39:17 2017 Sent: b'0.11894490465224017 NULL'
Wed Oct  4 06:39:18 2017 ====== Attempt #2
Wed Oct  4 06:39:18 2017 Receive: b'0.17709349465137436 NULL'
Wed Oct  4 06:39:18 2017 Remote token changed: 0.17709349465137436
Wed Oct  4 06:39:18 2017 Sent: b'0.11894490465224017 0.17709349465137436 ack'
Wed Oct  4 06:39:19 2017 ====== Attempt #3
Wed Oct  4 06:39:19 2017 Receive: b'0.17709349465137436 0.11894490465224017 ack'
Wed Oct  4 06:39:19 2017 Sent: b'0.11894490465224017 0.17709349465137436 ack'
Wed Oct  4 06:39:20 2017 Whee, hole was punched from both ends
Wed Oct  4 06:39:20 2017 Punched UDP hole to user@xxxxx.com:60001 successfully!
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:17 2017 Using port: 60001\n'
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:17 2017 Attempitng to punch to host: xxx.xxx.xxx.xxx on port: 60001\n'
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:17 2017 Binding local socket\n'
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:17 2017 Generated random token: 0.17709349465137436\n'
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:17 2017 ====== Attempt #0\n'
Wed Oct  4 06:39:21 2017 Background stdout: b"Wed Oct  4 03:39:17 2017 Sent: b'0.17709349465137436 NULL'\n"
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:18 2017 ====== Attempt #1\n'
Wed Oct  4 06:39:21 2017 Background stdout: b"Wed Oct  4 03:39:18 2017 Receive: b'0.11894490465224017 0.17709349465137436 ack'\n"
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:18 2017 Remote token changed: 0.11894490465224017\n'
Wed Oct  4 06:39:21 2017 Background stdout: b"Wed Oct  4 03:39:18 2017 Sent: b'0.17709349465137436 0.11894490465224017 ack'\n"
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:19 2017 Whee, hole was punched from both ends\n'
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:19 2017 Punched UDP hole to xx.xxx.xxx.xxx:60001 successfully!\n'
Wed Oct  4 06:39:21 2017 Background stdout: b'Wed Oct  4 03:39:20 2017 All threads done...\n'
Wed Oct  4 06:39:22 2017 All threads done...
"""

import os
import random
import socket
import subprocess
import sys
import threading
import time
from queue import Queue
from select import select


class PipeReader(threading.Thread):
    def __init__(self, fd, queue=None, autostart=True):
        self._fd = fd

        if queue is None:
            queue = Queue()

        self.queue = queue

        threading.Thread.__init__(self)

        if autostart:
            self.start()

    def run(self):
        while True:
            line = self._fd.readline()

            if not line:
                break

            self.queue.put(line)

    def eof(self):
        return not self.is_alive() and self.queue.empty()

    def readlines(self):
        while not self.queue.empty():
            yield self.queue.get()


def log(*args):
    print(time.asctime(), " ".join([str(x) for x in args]))


def run_self_on_remote(host, port):
    with open(__file__) as _self:
        process = subprocess.Popen(
            ["ssh", host, "python3", "-", str(port), "| cat"],
            stdin=_self,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout = PipeReader(process.stdout, autostart=True)
        stderr = PipeReader(process.stderr, autostart=True)

        while not stdout.eof() or not stderr.eof():
            for line in stdout.readlines():
                log("Background stdout: " + repr(line))

            for line in stderr.readlines():
                log("Background stderr: " + repr(line))

            time.sleep(0.25)

        stdout.join()
        stderr.join()

        process.stdout.close()
        process.stderr.close()


def puncher(host, port):
    try:
        host = host.split("@")[1]
    except:
        pass

    log("Attempitng to punch to host: %s on port: %s" % (host, port))

    log("Binding local socket")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", port))

    token = str(random.random())
    log("Generated random token:", token)
    remote_token = "NULL"

    sock.setblocking(0)
    sock.settimeout(2)

    tokens_synced = False

    for i in range(10):
        r, w, x = select([sock], [sock], [], 0)

        if tokens_synced:
            log("Whee, hole was punched from both ends")
            break

        log("====== Attempt #%s" % i)

        if r:
            data, addr = sock.recvfrom(1024)
            log("Receive:", data)
            data = data.decode()

            if remote_token == "NULL":
                remote_token = data.split()[0]
                log("Remote token changed:", remote_token)

            if len(data.split()) == 3:
                if data.split()[1] == token and data.split()[0] == remote_token:
                    tokens_synced = True

        if w:
            data = "%s %s" % (token, remote_token)

            if remote_token != "NULL":
                data += " ack"

            data = data.encode()
            sock.sendto(data, (host, port))
            log("Sent:", data)

        time.sleep(1)

    sock.close()

    return remote_token != "NULL"


if __name__ == "__main__":
    on_remote = False

    stdin = None
    if len(sys.argv) == 3:
        stdin = sys.argv[0]
        try:
            assert stdin == "-"
            host = sys.argv[1]
            port = int(sys.argv[2])

        except:
            stdin = False

    if not stdin:
        try:
            host = os.environ["SSH_CLIENT"].split()[0]
            port = int(sys.argv[1])
            log("Using port: %s" % port)
            on_remote = True

        except:
            host = sys.argv[1]
            port = int(sys.argv[2])

    def do_punch():
        if puncher(host, port):
            log("Punched UDP hole to %s:%s successfully!" % (host, port))

        else:
            log("Punch failed :(")

    try:
        puncher_thread = threading.Thread(target=do_punch)
        puncher_thread.setDaemon(True)
        puncher_thread.start()

        if not on_remote:
            log("Attempitng to start reverse punch on remote...")
            remote_puncher_thread = threading.Thread(
                target=run_self_on_remote,
                args=[host, port],
            )
            remote_puncher_thread.setDaemon(True)
            remote_puncher_thread.start()

        while True:
            time.sleep(1)
            if not puncher_thread.is_alive():

                if not on_remote and not remote_puncher_thread.is_alive():
                    break

                elif on_remote:
                    break

        log("All threads done...")

    except (KeyboardInterrupt, SystemExit):
        log("Caught interrupt, exiting...")
        sys.exit()
