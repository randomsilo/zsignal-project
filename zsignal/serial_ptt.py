"""RTS-based PTT control over a USB-serial interface (e.g. Digirig Mobile).

Requires pyserial: pip3 install pyserial
"""

import serial


class SerialPTT:
    """Holds a serial port open and drives RTS for PTT.

    Some USB-serial adapters glitch their control lines on open/close, so
    the port is opened once and held for the whole transmission rather
    than reopened per on/off call.
    """

    def __init__(self, port, baudrate=9600):
        self.port = port
        self.baudrate = baudrate
        self._ser = None

    def __enter__(self):
        # pyserial asserts RTS/DTR on open by default, which would briefly
        # key the radio; set them low before opening so PTT never glitches.
        self._ser = serial.Serial()
        self._ser.port = self.port
        self._ser.baudrate = self.baudrate
        self._ser.rts = False
        self._ser.dtr = False
        self._ser.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self._ser.rts = False
        finally:
            self._ser.close()

    def on(self):
        self._ser.rts = True

    def off(self):
        self._ser.rts = False
