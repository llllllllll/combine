from functools import wraps
import socket
import threading

from .logging import log


class Client:
    """An IRC client which sends messages to some handler object.

    Parameters
    ----------
    host : str
        The hostname of the server to connect to.
    port : int
        The port to connect to.
    username : str
        The username to log in with.
    password : str
        The password to log in with.
    default_channel : str
        The name of the channel to connect to. Note: do not include the hash.
    message_handler : Handler
        The message handler object.
    """
    def __init__(self,
                 host,
                 port,
                 username,
                 password,
                 default_channel,
                 message_handler):
        self.host = host
        self.port = port
        self.username = username = username.encode('ascii')
        self.password = password = password.encode('ascii')
        self.message_handler = message_handler

        self._socket = s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))

        s.send(b'PASS %b\r\n' % password)
        s.send(b'NICK %b\r\n' % username)
        s.send(b'USER %b %b %b :%b\r\n' % ((username,) * 4))
        s.send(b'JOIN #%b\r\n' % default_channel.encode('ascii'))

        self._write_lock = threading.Lock()
        self._running = True
        self._listen_thread = thread = threading.Thread(target=self._listen)
        thread.daemon = True
        thread.start()

        for periodic_task in message_handler._periodic_tasks:
            periodic_task.run(message_handler, self)

    def _check_running(f):
        """Decorator to check to see if the client is still running before
        dispatching to the underlying function.
        """
        @wraps(f)
        def dec(self, *args, **kwargs):
            if not self._running:
                raise ValueError('operation on closed client')

            return f(self, *args, **kwargs)

        return dec

    @_check_running
    def _pong(self, data):
        """Handle a response for a ``ping``

        Parameters
        ----------
        data : bytes
            The data sent by the server in the ``ping``.
        """
        with self._write_lock:
            self._socket.send(b'PONG %b\r\n' % data)

    def _handle_target(self, channel, user, msg):
        """The target function for the handler thread.

        Parameters
        ----------
        channel : str
            The channel the message was sent over.
        user : str
            The user who sent the message.
        msg : str
            The message itself.
        """
        try:
            return self.message_handler(self, user, channel, msg.strip())
        except Exception:
            log.exception('handler failure')
            pass

    @_check_running
    def _privmsg(self, channel, user, msg):
        """Handle a message.

        Parameters
        ----------
        channel : str
            The channel the message was sent over.
        user : str
            The user who sent the message.
        msg : str
            The message itself.
        """
        thread = threading.Thread(
            target=self._handle_target,
            args=(channel, user, msg),
        )
        thread.daemon = True
        thread.start()

    @_check_running
    def _ignore(self, user, data):
        pass

    def send(self, user, message):
        """Send a message to a user.

        Parameters
        ----------
        user : str
            The user to send the message to.
        message : str
            The message to send.

        Notes
        -----
        This function locks the write end of the socket; it is the only safe
        way to send messages back to the server. Handlers should always go
        through this method.
        """
        if '\n' in message:
            raise ValueError('cannot send messages with newlines')

        with self._write_lock:
            self._socket.send(b'PRIVMSG %b %b\r\n' % (
                user.encode('ascii'),
                message.encode('ascii'),
            ))

    def _listen(self):
        recv = self._socket.recv
        buffer = b''
        while self._running:
            buffer += recv(4096)
            # not splitlines, *sometimes* we get \r\n
            lines = buffer.split(b'\n')
            buffer = lines.pop()

            for line in lines:
                parts = line.strip().split(b' ', 3)

                if parts[0] == b'PING':
                    self._pong(parts[1])
                    continue

                if parts[1] != b'PRIVMSG':
                    continue

                name, _ = parts[0][1:].split(b'!')
                channel = parts[2].decode('utf-8')
                msg = parts[3].decode('utf-8')[1:]
                self._privmsg(channel, name.decode('utf-8'), msg)

    def stop(self):
        """Stop the client. Any messages being processed will be finished
        unless the main thread exits before they finish.
        """
        self._running = False

    def close(self):
        """Close the connections required by this client.

        Notes
        -----
        The client must be stopped first.
        """
        if self._running:
            raise ValueError('cannot close an active client')
        self._socket.close()

    def join(self):
        """Block until the client is stopped.
        """
        self._listen_thread.join()

    def run(self):
        with self:
            self.join()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.stop()
        self.join()
        self.close()
