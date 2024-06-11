"""Sets up the communication for the gas card device.

Author: Grayson Bellamy
Date: 2024-01-05
"""

from abc import ABC, abstractmethod
from collections.abc import ByteString

import anyio
import anyio.lowlevel
from anyserial import SerialStream
from anyserial.abstract import Parity, StopBits


class CommDevice(ABC):
    """Sets up the communication for the a OMRON power controller device."""

    def __init__(self, timeout: int) -> None:
        """Initializes the serial communication.

        Args:
            timeout (int): The timeout of the Alicat device.
        """
        self.timeout = timeout

    @abstractmethod
    async def _read(self, len: int) -> ByteString | None:
        """Reads the serial communication.

        Args:
            len (int): The length of the serial communication to read. One character if not specified.

        Returns:
            str: The serial communication.
        """
        pass

    @abstractmethod
    async def _write(self, command: str) -> None:
        """Writes the serial communication.

        Args:
            command (str): The serial communication.
        """
        pass

    @abstractmethod
    async def close(self):
        """Closes the serial communication."""
        pass

    @abstractmethod
    async def _readline(self) -> bytearray | None:
        """Reads the serial communication until end-of-line character reached.

        Returns:
            str: The serial communication.
        """
        pass

    @abstractmethod
    async def _write_readline(self, command: str) -> bytearray | None:
        """Writes the serial communication and reads the response until end-of-line character reached.

        Args:
            command (str): The serial communication.

        Returns:
            str: The serial communication.
        """
        pass


class SerialDevice(CommDevice):
    """Sets up the communication for the a OMRON power controller device using serial protocol."""

    def __init__(  # Need to verify Flow Control is set to 'none'
        self,
        port: str,
        baudrate: int = 57600,
        timeout: int = 500,  # Not present in manual
        databits: int = 7,
        parity: Parity = Parity.EVEN,
        stopbits: StopBits = StopBits.TWO,
        xonxoff: bool = False,  # Not present in manual
        rtscts: bool = False,  # Not present in manual
        exclusive: bool = False,  # Not present in manual
    ):
        """Initializes the serial communication.

        Args:
            port (str): The port to which the device is connected.
            baudrate (int): The baudrate of the device.
            timeout (int): The timeout of the device in ms.
            databits (int): The number of data bits.
            parity (Parity): The parity of the device.
            stopbits (StopBits): The of stop bits. Usually 1 or 2.
            xonxoff (bool): Whether the port uses xonxoff.
            rtscts (bool): Whether the port uses rtscts.
            exclusive (bool): Whether the port is exclusive.
        """
        super().__init__(timeout)

        self.timeout = timeout
        self.eol = b"\n"
        self.serial_setup = {
            "port": port,
            "exclusive": exclusive,
            "baudrate": baudrate,
            "bytesize": databits,
            "parity": parity,
            "stopbits": stopbits,
            # "xonxoff": xonxoff,
            # "rtscts": rtscts,
        }
        self.isOpen = False
        self.ser_devc = SerialStream(**self.serial_setup)

    async def _read(self, len: int | None = None) -> ByteString | None:
        """Reads the serial communication.

        Args:
            len (int): The length of the serial communication to read. One character if not specified.

        Returns:
            ByteString: The serial communication.
        """
        if len is None:
            len = self.ser_devc.in_waiting()
            if len == 0:
                return None
        if not self.isOpen:
            async with self.ser_devc:
                return await self.ser_devc.receive_some(len)
        else:
            return await self.ser_devc.receive_some(len)

    async def _write(self, command: str) -> None:
        """Writes the serial communication.

        Args:
            command (str): The serial communication.
        """
        if not self.isOpen:
            async with self.ser_devc:
                with anyio.move_on_after(self.timeout / 1000):
                    await self.ser_devc.send_all(command)
        else:
            with anyio.move_on_after(self.timeout / 1000):
                await self.ser_devc.send_all(command)
        return None

    async def _readline(self) -> bytearray:
        """Reads the serial communication until end-of-line character reached.

        Returns:
            str: The serial communication.
        """
        async with self.ser_devc:
            self.isOpen = True
            line = bytearray()
            while True:
                c = None
                with anyio.move_on_after(
                    self.timeout / 1000
                ):  # if keep reading none, then timeout
                    while c is None:  # Keep reading until a character is read
                        c = await self._read()
                        await anyio.lowlevel.checkpoint()
                if c is None:  # if we reach timeout,
                    break
                line += c
                if self.eol in line:
                    break
        self.isOpen = False
        return line

    async def _write_readall(self, command: str) -> list[str] | None:
        """Write command and read until timeout reached.

        Args:
            command (str): The serial communication.

        Returns:
            list: List of lines read from the device.
        """
        async with self.ser_devc:
            self.isOpen = True
            await self._write(command)
            line = bytearray()
            arr_line: list[str] = []
            while True:
                c = None
                with anyio.move_on_after(
                    self.timeout / 1000
                ):  # if keep reading none, then timeout
                    while c is None:  # Keep reading until a character is read
                        c = await self._read()
                        await anyio.lowlevel.checkpoint()
                if c is None:  # if we reach timeout,
                    break
                line += c
        arr_line = line.decode("ascii").splitlines()
        self.isOpen = False
        return arr_line

    async def _write_readline(self, command: str) -> bytearray:
        """Writes the serial communication and reads the response until end-of-line character reached.

        Parameters:
            command (str): The serial communication.

        Returns:
            str: The serial communication.
        """
        async with self.ser_devc:
            self.isOpen = True
            await self._write(command)
            line = bytearray()
            while True:
                c = None
                with anyio.move_on_after(
                    self.timeout / 1000
                ):  # if keep reading none, then timeout
                    while c is None:  # Keep reading until a character is read
                        c = await self._read()
                        await anyio.lowlevel.checkpoint()
                if c is None:  # if we reach timeout,
                    break
                line += c
                if b"\x03" in line:
                    break
        return line

    async def _flush(self) -> None:
        """Flushes the serial communication."""
        await self.ser_devc.discard_input()

    async def close(self) -> None:
        """Closes the serial communication."""
        self.isOpen = False
        await self.ser_devc.aclose()

    async def open(self) -> None:
        """Opens the serial communication."""
        self.isOpen = True
        await self.ser_devc.aopen()
