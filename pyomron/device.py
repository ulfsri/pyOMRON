from typing import Any, Union

import json
import re
from abc import ABC

import trio

from comm import CommDevice, SerialDevice
from trio import run
import trio


async def new_device(port: str, **kwargs: Any):
    """Creates a new device. Chooses appropriate device based on characteristics.

    Args:
        port (str): The port to connect to.
        **kwargs: Any

    Returns:
        Device: The new device.
    """
    if port.startswith("/dev/"):
        device = SerialDevice(port, **kwargs)

    return Omron(device, **kwargs)


class Omron(ABC):
    """Omron class.

    Todo:
        * Add function for controller attribute read
    """

    with open("codes.json") as f:
        codes = json.load(f)
    addresses = codes["addresses"][0]

    def __init__(self, device: SerialDevice, **kwargs: Any) -> None:
        """Initializes the Device object.

        Args:
            device (SerialDevice): The serial device object.
            id (str, optional): The device ID. Defaults to "A".
            **kwargs: Additional keyword arguments.
        """
        self._device = device

    async def _prepend(self, frame: list) -> list:
        """Prepends the frame with the device id.

        Args:
            frame (list): Command frame to prepend to

        Returns:
            list: Frame with prepended info
        """
        return [
            "\x02",  # STX
            "\x30",  # Unit No.
            "\x31",  # Unit No.
            "\x30",  # Sub-address
            "\x30",  # Sub-address
            "\x30",  # SID
        ] + frame

    async def _append(self, frame: list) -> list:
        """Appends the frame with the ETX.

        Args:
            frame (list): Command frame to append to

        Returns:
            list: Frame with appended info
        """
        return frame + ["\x03"]  # ETX

    async def _bcc_calc(self, frame: list) -> int:
        """Calculates the BCC of the frame.

        Args:
            frame (list): List of values in frame to use to find BCC

        Returns:
            bcc (int): Calculated BCC
        """
        bcc = 0
        for byte in frame[1:]:
            bcc ^= ord(byte)  # Take the XOR of all the bytes in the frame
        return bcc

    async def _check_end_code(self, ret: bytearray):
        """Checks if the end code is 00.

        If an error is present, the error name is printed.

        Args:
            ret (bytearray): Response from device

        Returns:
            str: Error if present, None if no error
        """
        error_codes = {
            bytes("00", "ascii"): "Normal Completion",
            bytes("0F", "ascii"): "FINS command error",
            bytes("10", "ascii"): "Parity error",
            bytes("11", "ascii"): "Framing error",
            bytes("12", "ascii"): "Overrun error",
            bytes("13", "ascii"): "BCC error",
            bytes("14", "ascii"): "Format error",
            bytes("16", "ascii"): "Sub-address error",
            bytes("18", "ascii"): "Frame length error",
        }
        error_code = ret[5:7]
        if error_code != bytes("00", "ascii"):
            print(error_codes.get(bytes(error_code), "Unknown Error"))
        return

    async def _check_response_code(self, ret: bytearray):
        """Checks if the response code is 0000.

        If an error is present, the error name is printed.

        Args:
            ret (bytearray): Response from device

        Returns:
            str: Error if present, None if no error
        """
        response_codes = {
            bytes("1001", "ascii"): "Command length too long",
            bytes("1002", "ascii"): "Command length too short",
            bytes("1003", "ascii"): "Number of elements/Number of data do not agree",
            bytes("1101", "ascii"): "Area Type Error",
            bytes("110B", "ascii"): "Response length too long",
            bytes("1100", "ascii"): "Parameter error",
            bytes("2203", "ascii"): "Operation error",
        }
        response_code = ret[11:15]
        if response_code != bytes("0000", "ascii"):
            print(response_codes.get(bytes(response_code), "Unknown Error"))
        return

    async def variable_area_write(self, command: str, set_values: float | list) -> None:
        """Changes set values.

        Args:
            command (str): The desired variable type and starting address
            set_values (float | list): The value the variable should be set to.
        """
        if isinstance(set_values, list):
            leng = len(set_values)  # Number of elements to write
        else:
            leng = 1
            set_values = [set_values]  # Convert to list if not already
        command_data = []

        for i, c in enumerate(command):
            command_data.append(c)  # Add each byte to the command_data list

        # Builds beginning portion of the FINS-mini command
        byte_list = (
            ["\x30", "\x31", "\x30", "\x32"]  # MRC  # MRC  # SRC  # SRC
            + command_data  # command
            + ["\x30", "\x30"]  # Bit Position  # Bit Position
        )

        # Add the number of elements to the FINS-mini command
        leng = f"{hex(leng)[2:]:0>4}".upper()  # Converts the number of elements to hex
        for i, c in enumerate(leng):
            byte_list.append(c)

        # Add the set values to the FINS-mini command
        for i, set_value in enumerate(set_values):
            # Checks for 'Status', 'Version', or 'Heater Burnout Threshold' commands
            # TODO: This 'if' statement needs to check for all addresses that are being written to, the command variable just stores the starting address
            if (
                command[1] == "E" and (int(command[5]) != 6 or int(command[4:5]) != 14)
            ) or (command[1] == "1" and int(command[5], 16) != 14):
                set_value = int(float(set_value * 10))

            if command[0] == "C":  # 8 bytes
                set_value = f"{hex(set_value)[2:]:0>8}".upper()
            else:  # 4 bytes
                set_value = f"{hex(set_value)[2:]:0>4}".upper()
            for i, c in enumerate(set_value):
                byte_list.append(c)

        # Build the communication frame
        # TODO: Can we wrap these prepend, appends, and bcc_calc into a single function?
        byte_list = await self._prepend(byte_list)
        byte_list = await self._append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([await self._bcc_calc(byte_list)])

        ret = await self._device._write_readline(byte)

        await self._check_end_code(ret)
        await self._check_response_code(ret)

        return

    async def variable_area_read(self, command: str, leng: int = 1) -> dict:
        """Reads set values.

        Args:
            command (str): The desired variable type and starting address
            leng (int): The number of elements to read. Defaults to 1.

        Returns:
            dict: Variable:Value pair for each variable read
        """
        command_data = []
        for i, c in enumerate(command):
            command_data.append(c)  # Add each byte to the command_data list

        # Builds beginning portion of the FINS-mini command
        byte_list = (
            ["\x30", "\x31", "\x30", "\x31"]  # MRC  # MRC  # SRC  # SRC
            + command_data  # command
            + ["\x30", "\x30"]  # Bit Position  # Bit Position
        )

        # Add the number of elements to the FINS-mini command
        leng = f"{hex(leng)[2:]:0>4}".upper()  # Converts the number of elements to hex
        for i, c in enumerate(leng):
            byte_list.append(c)

        # Build the communication frame
        # TODO: Can we wrap these prepend, appends, and bcc_calc into a single function?
        byte_list = await self._prepend(byte_list)
        byte_list = await self._append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([await self._bcc_calc(byte_list)])

        ret = await self._device._write_readline(byte)

        await self._check_end_code(ret)
        await self._check_response_code(ret)

        print_dict = {}
        ret = ret[15:-2]  # Removes everything but the set values from the response

        # Get metadata from the return
        var_type = byte[10:12].decode("ascii")  # Variable type read from
        read_start = int(byte[12:16], 16)  # Address to start reading from
        no_elements = int(byte[18:22], 16)  # Number of elements to read

        # Fill in the dictionary with the address: value pairs
        for i in range(no_elements):  # Loop through the each of the elements read
            addr = f"{hex(read_start + i)[2:]:0>4}".upper()  # Address of the element
            if var_type[0] == "C":  # The 8 bit case
                print_dict[self.addresses[var_type][addr]] = ret[
                    0 + 8 * i : 8 + 8 * i
                ].decode("ascii")
            elif var_type[0] == "8":  # The 4 bit case
                print_dict[self.addresses[var_type][addr]] = ret[
                    0 + 4 * i : 4 + 4 * i
                ].decode("ascii")
            else:
                print("Error in Variable Type")

        return print_dict

    async def controller_status_read(self) -> str:
        """Reads the operating and error status.

        Todo:
            * Make this function actually return the status instead of just bytearray

        Returns:
            str: Response from device
        """
        byte_list = ["\x30", "\x36", "\x30", "\x31"]
        byte_list = await self._prepend(byte_list)
        byte_list = await self._append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([await self._bcc_calc(byte_list)])
        ret = await self._device._write_readall(byte)
        await self._check_response_code(ret)
        return ret

    async def echo_back_test(self, test_input: int = 0) -> None:
        """Performs an echo back test.

        This is used for debugging purposes.

        Args:
            test_input (int): The number to echo back. Defaults to 0.
        """
        test_data = []
        while test_input > 0:
            test_data.insert(0, ascii(test_input % 10))
            test_input = int(test_input / 10)
        byte_list = [
            "\x30",
            "\x38",
            "\x30",
            "\x31",
        ] + test_data  # '0801' is echo-back command
        byte_list = await self._prepend(byte_list)
        byte_list = await self._append(byte_list)
        byte = bytes("".join(byte_list), "ascii")

        byte += bytes([await self._bcc_calc(byte_list)])
        ret = await self._device._write_readline(byte)
        await self._check_end_code(ret)
        ret = ret.hex()
        if ret[23] != "0" or ret[25] != "0" or ret[27] != "0" or ret[29] != "0":
            print("Error occured")
        print(f"Result = {bytes.fromhex(ret[30:-4]).decode('ascii')}")
        return

    async def get(self, comm: list) -> dict:
        """Gets the current value of the device.

        Todo:
            * Smartly manage reading if multiple sequential addresses are requested by using one call to variable_area_read() with necessary length

        Args:
            comm (list): List of variables for the device to retrieve

        Returns:
            dict: All variable:value pairs for each item in comm
        """
        # Makes a dictionary to store the results
        ret_dict = {}
        for c in comm:
            # Search through addresses to find the address for the comm
            for var_type, dict in self.addresses.items():
                for add, command in dict.items():
                    if c == command:
                        comm_add = var_type + add
            # Calls read and adds the result to the dictionary
            ret_dict.update(await self.variable_area_read(comm_add))
        return ret_dict

    async def set(self, comm: str | list, val: float | list) -> None:
        """Sets value of comm to val.

        Todo:
            * Make this accept a dictionary instead to write to multiple values at once

        Args:
            comm (str | list): Command to change
            val (float | list): New value for comm
        """
        # Search through addresses to find the address for the comm
        if not isinstance(comm, list):
            comm = [comm]
            val = [val]
        for i, c in enumerate(comm):
            for var_type, dict in self.addresses.items():
                for add, command in dict.items():
                    if c == command:
                        comm_add = var_type + add
            await self.variable_area_write(comm_add, val[i])  # Sets the value
        return