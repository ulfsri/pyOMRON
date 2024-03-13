from typing import Any, Union

import re
from abc import ABC

import trio

# from comm import CommDevice, SerialDevice
from comm import CommDevice, SerialDevice
from trio import run


async def new_device(port: str, id: str = "A", **kwargs: Any):
    """
    Creates a new device. Chooses appropriate device based on characteristics.
    """
    if port.startswith("/dev/"):
        device = SerialDevice(port, **kwargs)

    return Omron(device, id, **kwargs)


class Omron(ABC):
    """
    Omron class.
    """

    addresses = {  # These are all the Variable Type - Address combinations presented in the User Manual
        "CE": {
            "0000": "Input Monitor",
            "0001": "Internal Duty Monitor",
            "0002": "Output Monitor",
            "0003": "Phase Angle Monitor",
            "0004": "Current Monitor",
            "0005": "Total Run Time Monitor",
            "0006": "Status",
            "0007": "Heater characteristic of resistance",
            "0014": "Version",
        },
        "8E": {
            "0000": "Input Monitor",
            "0001": "Internal Duty Monitor",
            "0002": "Output Monitor",
            "0003": "Phase Angle Monitor",
            "0004": "Current Monitor",
            "0005": "Total Run Time Monitor",
            "0006": "Status",
            "0007": "Heater characteristic of resistance",
            "0014": "Version",
        },
        "C1": {
            "0000": "Communications Main Setting 1",
            "0001": "Communications Main Setting 2",
            "0002": "Communications Main Setting 3",
            "0003": "Communications Main Setting 4",
            "0004": "Communications Main Setting 5",
            "0005": "Communications Main Setting 6",
            "0006": "Communications Main Setting 7",
            "0007": "Communications Main Setting 8",
            "0008": "Internal Duty Setting",
            "0009": "Base-Up Value",
            "000A": "Soft-start Up Time",
            "000B": "Soft-start Down Time",
            "000C": "Output Upper Limit",
            "000D": "Output Lower Limit",
            "000E": "Heater Burnout Threshold",
            "000F": "Heater Characteristic Resistance for Phase Control",
            "0010": "Heater Characteristic Resistance for Optimum Cycle Control",
            "0011": "Heater Burnout Detection Lower Limit",
        },
        "81": {
            "0000": "Communications Main Setting 1",
            "0001": "Communications Main Setting 2",
            "0002": "Communications Main Setting 3",
            "0003": "Communications Main Setting 4",
            "0004": "Communications Main Setting 5",
            "0005": "Communications Main Setting 6",
            "0006": "Communications Main Setting 7",
            "0007": "Communications Main Setting 8",
            "0008": "Internal Duty Setting",
            "0009": "Base-Up Value",
            "000A": "Soft-start Up Time",
            "000B": "Soft-start Down Time",
            "000C": "Output Upper Limit",
            "000D": "Output Lower Limit",
            "000E": "Heater Burnout Threshold",
            "000F": "Heater Characteristic Resistance for Phase Control",
            "0010": "Heater Characteristic Resistance for Optimum Cycle Control",
            "0011": "Heater Burnout Detection Lower Limit",
        },
        "C3": {
            "0000": "Communications Data Length",
            "0001": "Communications Stop Bits",
            "0002": "Communications Parity",
            "0003": "Send Wait Time",
            "0004": "Communications Timeout Time",
            "0005": "Communications Unit Number",
            "0006": "Communications Baud Rate",
            "0007": "Communications Main Setting Number",
            "0008": "External Duty Input Enable/Disable",
            "0009": "Output Mode Selection",
            "000A": "Input Digital Filter Time Constant",
            "000B": "Input Signal Type",
            "000C": "Main Setting Automatic Input Selection",
            "000D": "Main Setting Manual Input Selection",
            "000E": "Control Method Default",
            "000F": "Main Setting Automatic/Manual Default",
            "0010": "Number of Alarms for Heater Burnout Detection",
            "0011": "Load Current Upper Limit",
            "0012": "Event Input Assignment",
            "0013": "Alarm Output Open in Alarm",
            "0014": "Heater Burnout Alarm Operation",
            "0015": "Total Run Time Exceeded Alarm Operation",
            "0016": "Total Run Time Alarm Set Value",
            "0017": "External Input Range Alarm Operation",
            "0018": "External Duty Input Alarm Operation",
            "0019": "SSR short circuit detection enabled",
            "001A": "SSR open failure detection",
            "001B": "CT failure detection",
        },
        "83": {
            "0000": "Communications Data Length",
            "0001": "Communications Stop Bits",
            "0002": "Communications Parity",
            "0003": "Send Wait Time",
            "0004": "Communications Timeout Time",
            "0005": "Communications Unit Number",
            "0006": "Communications Baud Rate",
            "0007": "Communications Main Setting Number",
            "0008": "External Duty Input Enable/Disable",
            "0009": "Output Mode Selection",
            "000A": "Input Digital Filter Time Constant",
            "000B": "Input Signal Type",
            "000C": "Main Setting Automatic Input Selection",
            "000D": "Main Setting Manual Input Selection",
            "000E": "Control Method Default",
            "000F": "Main Setting Automatic/Manual Default",
            "0010": "Number of Alarms for Heater Burnout Detection",
            "0011": "Load Current Upper Limit",
            "0012": "Event Input Assignment",
            "0013": "Alarm Output Open in Alarm",
            "0014": "Heater Burnout Alarm Operation",
            "0015": "Total Run Time Exceeded Alarm Operation",
            "0016": "Total Run Time Alarm Set Value",
            "0017": "External Input Range Alarm Operation",
            "0018": "External Duty Input Alarm Operation",
            "0019": "SSR short circuit detection enabled",
            "001A": "SSR open failure detection",
            "001B": "CT failure detection",
        },
    }

    def __init__(
        self, device: SerialDevice, dev_info: dict, id: str = "A", **kwargs: Any
    ) -> None:
        self._device = device
        self._id = id
        self._df_format = None
        self._df_units = None

    def __prepend(self, frame: list) -> list:
        """
        Prepends the frame with the device id.
        """
        return [
            "\x02",
            "\x30",
            "\x31",
            "\x30",
            "\x30",
            "\x30",
        ] + frame  # [STX, Unit No., Unit No., Sub-address, Sub-addres, SID]

    def __append(self, frame: list) -> list:
        """
        Apends the frame with the ETX.
        """
        return frame + ["\x03"]

    def __bcc_calc(self, command: list) -> int:
        """
        Calculates the BCC of the command.
        """
        bcc = 0
        for i in range(len(command)):
            if i != 0:
                bcc ^= ord(command[i])  # Take the XOR of all the bytes in the command
        return bcc

    def __end_code(self, ret: str):
        """
        Checks if the end code is 00.
        """
        if ret[11] != "0" and ret[13] != "0":  #'00' is the 'Normal Completion' end code
            if ret[11] == "0" and ret[13] == "F":
                print("FINS Command error")
            elif ret[11] == "1" and ret[13] == "0":
                print("Parity Error")
            elif ret[11] == "1" and ret[13] == "1":
                print("Framing Error")
            elif ret[11] == "1" and ret[13] == "2":
                print("Overrun Error")
            elif ret[11] == "1" and ret[13] == "3":
                print("BCC Error")
            elif ret[11] == "1" and ret[13] == "4":
                print("Format Error")
            elif ret[11] == "1" and ret[13] == "6":
                print("Sub-address Error")
            elif ret[11] == "1" and ret[13] == "8":
                print("Frame Length Error")
            else:
                print("Unknown Error")
        return

    async def variable_area_write(self, command: str, set_values: float):
        """
        Changes set values
        """
        command_data = []
        for i, c in enumerate(
            command
        ):  # Convert every character of the command to a byte
            command_data.append(c)  # Add each byte to the command_data list
        no_elements = ["\x30", "\x30", "\x30", "\x31"]  # Writes to 1 element per call
        byte_list = (
            ["\x30", "\x31", "\x30", "\x32"] + command_data + ["\x30", "\x30"]
        )  # [MRC, MRC, SRC, SRC, command, Bit Position, Bit Position]
        for i, c in enumerate(no_elements):
            byte_list.append(c)
        if (
            command[1] == "E" and (int(command[5]) != 6 or int(command[4:5]) != 14)
        ) or (
            command[1] == "1" and int(command[5], 16) != 14
        ):  # Checks for 'Status', 'Version', or 'Heater Burnout Threshold'
            set_values = int(
                float(set_values) * 10
            )  # Otherwise makes data ten times actual value
        set_values = hex(set_values)
        set_values = set_values[
            set_values.index("x") + 1 :
        ].upper()  # Removes '0x' from the hex value and makes it uppercase
        L = 4  # Default length is 4
        if command[0] == "C":  # If the command is 'C_', there are 8 bytes instead
            L = 8
        while len(set_values) < L:
            set_values = "0" + set_values  # Prepend 0's to make command length 4
        for i, c in enumerate(set_values):
            byte_list.append(c)
        byte_list = self.__prepend(byte_list)
        byte_list = self.__append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes(
            [self.__bcc_calc(byte_list)]
        )  # Adds bcc to the end of the command
        ret = await self._device._write_readline(
            byte
        )  # Writes the command and reads the response
        ret = ret.hex()
        self.__end_code(ret)
        if (
            ret[23] != "0" or ret[25] != "0" or ret[27] != "0" or ret[29] != "0"
        ):  # Checks response code, '0000' is 'Normal Completion'
            print("Error occured")
            if ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "1":
                print("Command length too long")
            elif (
                ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "2"
            ):
                print("Command length too short")
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "1"
            ):
                print("Area Type Error")
            elif (
                ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "3"
            ):
                print("Number of elements/Number of data do not agree")
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "0"
            ):
                print("Parameter error")
            elif (
                ret[23] == "2" and ret[25] == "2" and ret[27] == "0" and ret[29] == "3"
            ):
                print("Operation error")
            else:
                print("Unknown Error")
        else:
            byte = byte.hex()
            byte = byte[20:-4]  # Removes everything but the address
            byte = bytes.fromhex(byte)  # Converts the hex string to bytes
            byte.decode("ASCII")  # Formats byte to ASCII
            byte = str(byte, encoding="ascii")  # Converts byte to string
            for i in range(int(byte[8:12])):
                # Prints the address that was called
                print(
                    f"{self.addresses[byte[0:2]][list(self.addresses[byte[0:2]])[list(self.addresses[byte[0:2]]).index(byte[2:6])+i]]} set"
                )

    async def variable_area_read(self, command: str):
        """
        Reads set values.
        """
        command_data = []
        for i, c in enumerate(
            command
        ):  # Convert every character of the command to a byte
            command_data.append(c)  # Add each byte to the command_data list
        byte_list = (
            ["\x30", "\x31", "\x30", "\x31"] + command_data + ["\x30", "\x30"]
        )  # [MRC, MRC, SRC, SRC, command, Bit Position, Bit Position]
        no_elements = ["\x30", "\x30", "\x30", "\x31"]  # Reads to 1 element per call
        for i, c in enumerate(no_elements):
            byte_list.append(c)
        byte_list = self.__prepend(byte_list)
        byte_list = self.__append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([self.__bcc_calc(byte_list)])
        ret = await self._device._write_readline(byte)
        ret = ret.hex()
        self.__end_code(ret)
        print_dict = {}  # Creates an empty dictionary for displaying the result
        if (
            ret[23] != "0" or ret[25] != "0" or ret[27] != "0" or ret[29] != "0"
        ):  # Checks response code, '0000' is 'Normal Completion'
            print("Error occured")
            if ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "1":
                print("Command length too long")
            elif (
                ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "2"
            ):
                print("Command length too short")
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "1"
            ):
                print("Area Type Error")
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "B"
            ):
                print("Response length too long")
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "0"
            ):
                print("Parameter error")
            elif (
                ret[23] == "2" and ret[25] == "2" and ret[27] == "0" and ret[29] == "3"
            ):
                print("Operation error")
            else:
                print("Unknown Error")
        else:
            ret = ret[30:-4]  # Removes everything but the set values from the response
            byte = byte.hex()
            byte = byte[20:-4]  # Removes everything but the address
            byte = bytes.fromhex(byte)
            byte.decode("ASCII")
            byte = str(byte, encoding="ascii")
            for i in range(
                int(byte[8:12])
            ):  # For each element in response (should be one)
                if byte[0:1] == "C":  # The eight bit case
                    print_dict[
                        self.addresses[byte[0:2]][
                            list(self.addresses[byte[0:2]])[
                                list(self.addresses[byte[0:2]]).index(byte[2:6]) + i
                            ]
                        ]
                    ] = bytes.fromhex(ret[0 + 16 * i : 16 + 16 * i]).decode("ascii")
                elif byte[0:1] == "8":  # The 4 bit case
                    print_dict[
                        self.addresses[byte[0:2]][
                            list(self.addresses[byte[0:2]])[
                                list(self.addresses[byte[0:2]]).index(byte[2:6]) + i
                            ]
                        ]
                    ] = bytes.fromhex(ret[0 + 8 * i : 8 + 8 * i]).decode("ascii")
                else:
                    print("Error in Variable Type")
        return print_dict  # returns the dictionary with the adress: value pair

    async def controller_status_read(self):
        """
        Reads the operating and error status.
        """
        byte_list = ["\x30", "\x36", "\x30", "\x31"]
        byte_list = self.__prepend(byte_list)
        byte_list = self.__append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([self.__bcc_calc(byte_list)])
        ret = await self._device._write_readall(byte.decode("ascii"))
        return

    async def echo_back_test(self):
        """
        Performs an echo back test.
        """
        test_input = int(input("Enter test data (0-200) >"))
        test_data = []
        while test_input > 0:
            test_data.insert(0, ascii(test_input % 10))
            test_input = int(test_input / 10)
        byte_list = ["\x30", "\x38", "\x30", "\x31"] + test_data
        byte_list = self.__prepend(byte_list)
        byte_list = self.__append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([self.__bcc_calc(byte_list)])
        ret = await self._device._write_readline(byte)
        ret = ret.hex()
        self.__end_code(ret)
        if ret[23] != "0" or ret[25] != "0" or ret[27] != "0" or ret[29] != "0":
            print("Error occured")
        print(f"Result = {bytes.fromhex(ret[30:-4]).decode('ascii')}")
        return

    async def get(self, comm: list):
        """
        Gets the current value of the device.
        """
        ret_dict = {}  # Makes a dictionary to store the results
        for c in comm:
            for var_type, dict in self.addresses.items():
                for add, command in dict.items():
                    if c == command:
                        comm_add = (
                            var_type + add
                        )  # Search through addresses to find the address for the comm
            ret_dict.update(
                await self.variable_area_read(comm_add)
            )  # Adds the result to the dictionary
        return ret_dict

    async def set(self, comm, val):
        """
        Sets value of comm to val.

        Args:
            comm (_type_): _description_
            val (_type_): _description_
        """
        for var_type, dict in self.addresses.items():
            for add, command in dict.items():
                if comm == command:
                    comm_add = (
                        var_type + add
                    )  # Search through addresses to find the address for the comm
        await self.variable_area_write(comm_add, val)  # Sets the value
        return
