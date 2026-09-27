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
        self._ser = serial.Serial(self.port, baudrate=self.baudrate)
        self._ser.rts = False
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
