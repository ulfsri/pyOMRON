"""Module for the OMRON power controller device.

Raises:
    ValueError: If the device is not a G3PW device.

Returns:
    Device: The new device.
"""

import importlib
import json
from abc import ABC
from typing import Any, Self

from .comm import SerialDevice


class Omron(ABC):
    """Omron class."""

    codes = importlib.resources.files("pyomron").joinpath("codes.json")
    with open(codes) as f:
        codes = json.load(f)
    addresses = codes["addresses"][0]
    C383_notation = codes["C383_notation"][0]
    status_labels = codes["status_labels"]

    def __init__(self, device: SerialDevice, unit_no: int = 1, **kwargs: Any) -> None:
        """Initializes the Device object.

        Args:
            device (SerialDevice): The serial device object.
            unit_no (int, optional): The device unit number. Defaults to 1.
            **kwargs: Additional keyword arguments.
        """
        self._device = device
        self._device_info = None
        self._unit_no = unit_no

    @classmethod
    async def new_device(cls, port: str, unit_no: int = 1, **kwargs: Any) -> Self:
        """Creates a new device. Chooses appropriate device based on characteristics.

        Example:
            dev = run(Omron.new_device, "/dev/ttyUSB6")

        Args:
            port (str): The port to connect to.
            unit_no (int, optional): The unit number. Defaults to 1.
            **kwargs: Any

        Returns:
            Device: The new device.
        """
        if port.startswith("/dev/"):
            device = SerialDevice(port, **kwargs)
        byte_list = [
            "\x30",
            "\x35",
            "\x30",
            "\x33",
        ]  # Command for controller attribute read
        byte_list = await cls._prepend(byte_list, unit_no)
        byte_list = await cls._append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([await cls._bcc_calc(byte_list)])
        resp = await device._write_readline(byte)
        await cls._check_end_code(resp)
        await cls._check_response_code(resp)
        ret = resp[15:-6].decode("ascii")
        # Chek using is_model class to see if it matches G3PW
        if await cls._is_model(ret):
            return cls(device, unit_no, **kwargs)
        else:
            raise ValueError("Device is not G3PW")

    @classmethod
    async def _prepend(cls, frame: list[str], unit_no: int = 1) -> list[str]:
        """Prepends the frame with the device id.

        Args:
            frame (list[str]): Command frame to prepend to
            unit_no (int, optional): The unit number. Defaults to 1.

        Returns:
            list[str]: Frame with prepended info
        """
        if unit_no and type(unit_no) != int:
            unit_no = int(unit_no, 16)
        n = hex(unit_no)
        digs = list(n[2:].upper())
        if len(digs) < 2:
            digs.insert(0, "\x30")
        return (
            [
                "\x02"  # STX
            ]
            + digs  # Unit No.
            + [
                "\x30",  # Sub-address
                "\x30",  # Sub-address
                "\x30",  # SID
            ]
            + frame
        )

    @classmethod
    async def _append(cls, frame: list[str]) -> list[str]:
        """Appends the frame with the ETX.

        Args:
            frame (list[str]): Command frame to append to

        Returns:
            list[str]: Frame with appended info
        """
        return frame + ["\x03"]  # ETX

    @classmethod
    async def _bcc_calc(cls, frame: list[str]) -> int:
        """Calculates the BCC of the frame.

        Args:
            frame (list[str]prepend): List of values in frame to use to find BCC

        Returns:
            bcc (int): Calculated BCC
        """
        bcc = 0
        for byte in frame[1:]:
            bcc ^= ord(byte)  # Take the XOR of all the bytes in the frame
        return bcc

    @classmethod
    async def _is_model(cls, model: str) -> bool:
        """Checks if the device is the correct model.

        Args:
            model (str): The model to check against

        Returns:
            bool: True if the model is correct, False otherwise
        """
        return model[0:4] == "G3PW"

    async def _comm_frame(self, frame: list[str]) -> bytes:
        """Builds the communication frame.

        Args:
            frame (list[str]): Command frame to build

        Returns:
            list: Communication frame
        """
        byte_list = await self._prepend(frame, self._unit_no)
        byte_list = await self._append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([await self._bcc_calc(byte_list)])
        return byte

    @classmethod
    async def _check_end_code(cls, ret: bytearray) -> None:
        """Checks if the end code is 00.

        If an error is present, the error name is printed.

        Args:
            ret (bytearray): Response from device

        Raises:
            ValueError: If an error is present

        Returns:
            None
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
            # print(error_code)
            # print(error_codes.get(bytes(error_code), "Unknown Error"))
            raise ValueError(f"{error_codes.get(bytes(error_code), "Unknown Error")}")
        return

    @classmethod
    async def _check_response_code(cls, ret: bytearray) -> None:
        """Checks if the response code is 0000.

        If an error is present, the error name is printed.

        Args:
            ret (bytearray): Response from device

        Raises:
            ValueError: If an error is present

        Returns:
            None
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
            # print(response_codes.get(bytes(response_code), "Unknown Error"))
            raise ValueError(
                f"{response_codes.get(bytes(response_code), "Unknown Error")}"
            )
        return

    async def _variable_area_write(
        self, var_addr: str, set_values: float | list[float]
    ) -> None:
        """Changes set values.

        Automatically handles if multiple consecutive addresses are being written to.

        Args:
            var_addr (str): The desired variable type and starting address
            set_values (float | list[float]): The value the variable should be set to.
        """
        if isinstance(set_values, list):
            num_elem = len(set_values)  # Number of elements to write
        else:
            num_elem = 1
            set_values = [set_values]  # Convert to list if not already
        command_data = []

        for i, c in enumerate(var_addr):
            command_data.append(c)  # Add each byte to the command_data list

        # Builds beginning portion of the FINS-mini command
        byte_list = (
            ["\x30", "\x31", "\x30", "\x32"]  # MRC  # MRC  # SRC  # SRC
            + command_data  # command
            + ["\x30", "\x30"]  # Bit Position  # Bit Position
        )

        # Add the number of elements to the FINS-mini command
        num_elem = (
            f"{hex(num_elem)[2:]:0>4}".upper()
        )  # Converts the number of elements to hex string
        for i, c in enumerate(num_elem):
            byte_list.append(c)

        # Add the set values to the FINS-mini command
        for i, set_value in enumerate(set_values):
            # Checks for 'Status', 'Version', or 'Heater Burnout Threshold' commands
            # TODO: This 'if' statement needs to check for all addresses that are being written to, the command variable just stores the starting address
            # Or maybe we need to come up with a better system for doing this. It could be done in the set() function by the address name and then passed to the write function with the value appropriately scaled
            if (
                var_addr[1] == "E"
                and (int(var_addr[5]) != 6 or int(var_addr[4:5]) != 14)
            ) or (var_addr[1] == "1" and int(var_addr[5], 16) != 14):
                set_value = int(float(set_value * 10))

            # Converts the set value to a hex string
            if var_addr[0] == "C":  # 8 bytes
                set_value = f"{hex(set_value)[2:]:0>8}".upper()
            elif var_addr[0] == "8":  # 4 bytes
                set_value = f"{hex(set_value)[2:]:0>4}".upper()
            for i, c in enumerate(set_value):
                byte_list.append(c)

        # Build the communication frame
        byte = await self._comm_frame(byte_list)

        resp = await self._device._write_readline(byte)

        await self._check_end_code(resp)
        await self._check_response_code(resp)

        return

    async def _variable_area_read(
        self, var_addr: str, num_elem: int = 1
    ) -> dict[str, str | float]:
        """Reads set values.

        Args:
            var_addr (str): The desired variable type and starting address
            num_elem (int): The number of elements to read. Defaults to 1.

        Returns:
            dict[str, str | float]: Variable:Value pair for each variable read
        """
        command_data = []
        ret_dict = {}

        for i, c in enumerate(var_addr):
            command_data.append(c)  # Add each byte to the command_data list

        # Builds beginning portion of the FINS-mini command
        byte_list = (
            ["\x30", "\x31", "\x30", "\x31"]  # MRC  # MRC  # SRC  # SRC
            + command_data  # command
            + ["\x30", "\x30"]  # Bit Position  # Bit Position
        )

        # Converts the number of elements to hex
        num_elem = f"{hex(num_elem)[2:]:0>4}".upper()
        # Add the number of elements to the FINS-mini command
        for i, c in enumerate(num_elem):
            byte_list.append(c)

        # Build the communication frame, prepends and appends
        byte = await self._comm_frame(byte_list)

        resp = await self._device._write_readline(byte)

        await self._check_end_code(resp)
        await self._check_response_code(resp)

        resp = resp[15:-2]  # Removes everything but the set values from the response

        # Get metadata from the return. Questionable if we need this because it's given in the function call
        var_type = byte[10:12].decode("ascii")  # Variable type read from
        read_start = int(byte[12:16], 16)  # Address to start reading from
        num_elem = int(byte[18:22], 16)  # Number of elements to read

        # Fill in the dictionary with the address: value pairs
        for i in range(num_elem):  # Loop through the each of the elements read
            addr = f"{hex(read_start + i)[2:]:0>4}".upper()  # Address of the element
            if var_type[0] == "C":  # The 8 bit case
                ret_dict[self.addresses[var_type][addr]] = int(
                    resp[0 + 8 * i : 8 + 8 * i].decode("ascii"), 16
                )
            elif var_type[0] == "8":  # The 4 bit case
                ret_dict[self.addresses[var_type][addr]] = int(
                    resp[0 + 4 * i : 4 + 4 * i].decode("ascii"), 16
                )
            else:
                # print("Error in Variable Type")
                raise ValueError("Variable Type Error")

        # Convert data to readable notation
        for key, value in ret_dict.items():
            if var_type[1] in ["E", "1"]:
                if key == "Version":
                    ret_dict[key] = value / 100
                elif key == "Status":
                    return await self.status(value)
                elif key == "Heater Burnout Threshold":
                    ret_dict[key] = value
                else:
                    ret_dict[key] = value / 10
            else:
                try:
                    note = self.C383_notation[key][str(value)]
                except KeyError:
                    note = None
                if note:
                    ret_dict[key] = note
                elif key in [
                    "Input Digital Filter Time Constant",
                    "Load Current Upper Limit",
                    "Total Run Time Alarm Set Value",
                ]:
                    ret_dict[key] = value / 10
                else:
                    ret_dict[key] = value
        return ret_dict

    async def status(self, value: str) -> dict[str, str]:
        """Reads the operating and error status from a bit field.

        Args:
            value (str): The bit field to read from

        Returns:
            dict[str, str]: Value of each Protection/Error Operation
        """
        e_m = {0: "No Error", 1: "Error"}
        p_m = {0: "OFF", 1: "ON"}
        status = ["Q"] * 32
        for i in range(32):
            if i in [7, 12, 13, 14, 15]:
                continue
            elif i < 16:
                status[i] = e_m[(value >> i) & 1]
            elif i == 19:
                status[i] = (
                    "Initial Setting Level" if (value >> i) & 1 else "Operation Level"
                )
            elif i == 20:
                status[i] = "Manual" if (value >> i) & 1 else "Automatic"
            elif i == 21:
                status[i] = (
                    "Optimum Cycle Control" if (value >> i) & 1 else "Phase Control"
                )
            elif i < 32:
                status[i] = p_m[(value >> i) & 1]
        ret_dict = dict(zip(self.status_labels, status))
        del ret_dict["Not used."]
        return ret_dict

    async def controller_attribute_read(self) -> str:
        """Reads the controller attribute.

        Returns:
            str: Response from device
        """
        byte_list = [
            "\x30",
            "\x35",
            "\x30",
            "\x33",
        ]  # Command for controller attribute read
        byte = await self._comm_frame(byte_list)
        resp = await self._device._write_readline(byte)
        await self._check_response_code(resp)
        ret = resp[15:-6].decode("ascii")
        self._device_info = ret
        return ret

    async def controller_status_read(self) -> str:
        """Reads the operating and error status.

        Returns:
            str: Response from device
        """
        byte_list = [
            "\x30",
            "\x36",
            "\x30",
            "\x31",
        ]  # Command for controller status read
        byte = await self._comm_frame(byte_list)
        resp = await self._device._write_readline(byte)
        await self._check_response_code(resp)
        ret = resp[15:-4].decode("ascii")
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
        byte = await self._comm_frame(byte_list)
        resp = await self._device._write_readline(byte)
        await self._check_end_code(resp)
        resp = resp.hex()
        if resp[23] != "0" or resp[25] != "0" or resp[27] != "0" or resp[29] != "0":
            # print("Error occured")
            raise RuntimeError("Unknown Error")
        # print(f"Result = {bytes.fromhex(resp[30:-4]).decode('ascii')}")
        return

    async def get(
        self, comm: list[str] = "", ignoreError: bool = False
    ) -> dict[str, str | float]:
        """Gets the current value of the device.

        Example:
            df = run(dev.get, ["Version", "Communications Main Setting 1", "Communications Parity"])
            df = run(dev.get, "Status")

        Args:
            comm (list[str]): List of variables for the device to retrieve
            ignoreError (bool): If False, not finding one value raises an error. If True, everything else returned. Defaults to False.

        Returns:
            dict[str, str | float]: All variable:value pairs for each item in comm
        """
        if not comm:
            return await self.monitors()
        if not isinstance(comm, list):
            comm = [comm]
        # Makes a dictionary to store the results
        ret_dict = {}
        comm_list = []
        for c in comm:
            # Search through addresses to find the address for the comm
            for var_type, dict in self.addresses.items():
                for add, command in dict.items():
                    if c == command:
                        comm_add = var_type + add
                        if comm_add == "8E0006":
                            comm_add = "CE0006"
                        if (
                            "8" + comm_add[1:] not in comm_list
                            and "C" + comm_add[1:] not in comm_list
                        ):
                            comm_list.append(comm_add)
            # Calls read and adds the result to the dictionary
        comm_list.sort()
        # print(comm_list)
        i = 0
        while i <= len(comm_list) - 1:
            k = 1
            # print(f"Looking from: {hex(int(comm_list[i], 16))[2:].upper()}")
            for j in range(8):
                if hex(int(comm_list[i], 16) + j)[2:].upper() in comm_list:
                    # print("Found: " + hex(int(comm_list[i], 16) + j)[2:].upper())
                    idx = comm_list.index(hex(int(comm_list[i], 16) + j)[2:].upper())
                    k = j + 1
            # print(f"Calling read with {comm_list[i]}, length {k}")
            ret_dict.update(await self._variable_area_read(comm_list[i], k))
            if k > 1:
                i = idx
            i += 1
        for c in list(ret_dict.keys()):
            if c not in comm and c not in self.status_labels:
                del ret_dict[c]
        if (
            "Status" not in comm
            and len(comm) != len(ret_dict)
            or "Status" in comm
            and len(comm) != len(ret_dict) - 16
        ) and not ignoreError:
            # print(f"comm is {comm}, ret_dict is {ret_dict}")
            # print(f"Error: Not all values were read.")
            raise KeyError("Not all values were read.")
        return ret_dict

    async def set(self, comm: dict[str, str | float]) -> None:
        """Sets value of comm to val.

        Todo:
            * Could also smartly manage writing if multiple sequential addresses are requested by using one call to variable_area_write() with necessary length but this is low priority because it's not likely we would run into this scenario often

        Example:
            df = run(dev.set, {"Communications Parity": "Odd", 'Output Upper Limit': 100})

        Args:
            comm (dict[str, str | float]): Command to change in form comm:val
        """
        # Search through addresses to find the address for the comm
        for c in list(comm.keys()):
            for var_type, dict in self.addresses.items():
                for add, command in dict.items():
                    if c == command:
                        comm_add = var_type + add
            for var_type, dict in self.C383_notation.items():
                for add, command in dict.items():
                    if comm[c] == command:
                        comm[c] = add
            await self._variable_area_write(comm_add, int(comm[c]))  # Sets the value
        return

    async def heat(self, setpoint: float) -> None:
        """Convenience: Sets the heater setpoint.

        Example:
            df = run(dev.heat, 0.0)

        Args:
            setpoint (float): The desired setpoint
        """
        await self.set({"Communications Main Setting 1": setpoint})
        return

    async def monitors(self) -> dict[str, float]:
        """Convenience: Gets the current monitor values.

        Example:
            df = run(dev.monitors)

        Args:
            setpoint (dict[str, float]): The desired setpoint
        """
        return await self._variable_area_read("8E0000", 6)
