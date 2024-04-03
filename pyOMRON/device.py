from typing import Any, Union

import re
from abc import ABC

import trio

# from comm import CommDevice, SerialDevice
from comm import CommDevice, SerialDevice
from trio import run
import trio


async def new_device(port: str, id: str = "A", **kwargs: Any):
    """Creates a new device. Chooses appropriate device based on characteristics.
        
    Args:
        **kwargs: Any

    Returns:
        Device: The new device.        
    """
    if port.startswith("/dev/"):
        device = SerialDevice(port, **kwargs)

    return Omron(device, id, **kwargs)


class Omron(ABC):
    """Omron class."""
    
    with open("codes.json") as f:
        codes = json.load(f)
    commands = codes["addresses"][0]

    def __init__(
        self, device: SerialDevice, dev_info: dict, id: str = "A", **kwargs: Any
    ) -> None:
        """Initializes the Device object.

        Args:
            device (SerialDevice): The serial device object.
            dev_info (dict): The device information.
            id (str, optional): The device ID. Defaults to "A".
            **kwargs: Additional keyword arguments.
        """
        self._device = device
        self._id = id
        self._df_format = None
        self._df_units = None

    def __prepend(self, frame: list) -> list:
        """Prepends the frame with the device id.
        
        Args:
            frame (list): command frame to prepend to
        
        Returns:
            list: frame with prepended info
        """
        return [
            "\x02",  # STX
            "\x30",  # Unit No.
            "\x31",  # Unit No.
            "\x30",  # Sub-address
            "\x30",  # Sub-address
            "\x30",  # SID
        ] + frame

    def __append(self, frame: list) -> list:
        """Apends the frame with the ETX.
        
        Args:
            frame (list): command frame to append to
        
        Returns:
            list: frame with appended info
        """
        return frame + ["\x03"]  # ETX

    def __bcc_calc(self, command: list) -> int:
        """Calculates the BCC of the command.
        
        Args:
            command (list): characters to use to find BCC
        
        Returns:
            int: BCC calculation
        """
        bcc = 0
        for i in range(len(command)):
            if i != 0:
                #  Take the XOR of all the bytes in the command
                bcc ^= ord(command[i])
        return bcc

    def __end_code(self, ret: str):
        """Checks if the end code is 00.

        If en error is present, the error name is printed.
        
        Args:
            ret (str): Response from device
        
        Returns:
            str: Error if present, None if no error
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

    async def variable_area_write(self, command: str, set_values: float) -> None:
        """Changes set values.
        
        Args:
            command (str): describes the action the device should take
            set_values (float): the value the variable should be set to.
        """
        command_data = []
        # Convert every character of the command string to a byte
        for i, c in enumerate(command):
            # Add each byte to the command_data list
            command_data.append(c)
        # Write to 1 element per call
        no_elements = ["\x30", "\x30", "\x30", "\x31"]  # "0001"
        # The byte lists tracks the characters in the command
        byte_list = (
            ["\x30", "\x31", "\x30", "\x32"]  # MRC  # MRC  # SRC  # SRC
            + command_data # command  
            + ["\x30", "\x30"]  # Bit Position  # Bit Position
        )
        # Add the number of elements to the byte list
        for i, c in enumerate(no_elements):
            byte_list.append(c)
        # Checks for 'Status', 'Version', or 'Heater Burnout Threshold' commands
        if (
            command[1] == "E" and (int(command[5]) != 6 or int(command[4:5]) != 14)
        ) or (command[1] == "1" and int(command[5], 16) != 14):
            # Otherwise makes data ten times actual value
            set_values = int(float(set_values) * 10)
        # Converts the input values to hex
        set_values = hex(set_values)
        # Removes '0x' from the hex value and makes it uppercase
        set_values = set_values[set_values.index("x") + 1 :].upper()
        # Sets default length to 4
        L = 4
        # If the command is 'C_', length is 8 bytes instead
        if command[0] == "C":
            L = 8
        # Prepend 0's to make command correct length
        while len(set_values) < L:
            set_values = "0" + set_values
        # Add the set values to the byte list
        for i, c in enumerate(set_values):
            byte_list.append(c)
        byte_list = self.__prepend(byte_list)
        byte_list = self.__append(byte_list)
        # Convert byte list to an ascii string
        byte = bytes("".join(byte_list), "ascii")
        # Compute and append the bcc
        byte += bytes([self.__bcc_calc(byte_list)])
        # Writes the command and reads the response
        ret = await self._device._write_readline(byte)
        # Converts the response to a hex string
        ret = ret.hex()
        # Checks for an error
        self.__end_code(ret)
        # Checks response code, '0000' is 'Normal Completion'
        if ret[23] != "0" or ret[25] != "0" or ret[27] != "0" or ret[29] != "0":
            print("Error occured")
            if ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "1":
                print("Command length too long")  # '1001'
            elif (
                ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "2"
            ):
                print("Command length too short")  # '1002'
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "1"
            ):
                print("Area Type Error")  # '1101'
            elif (
                ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "3"
            ):
                print("Number of elements/Number of data do not agree")  # '1003'
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "0"
            ):
                print("Parameter error")  # '1100'
            elif (
                ret[23] == "2" and ret[25] == "2" and ret[27] == "0" and ret[29] == "3"
            ):
                print("Operation error")  # '2203'
            else:
                print("Unknown Error")  # Any other code
        # If no error occurs
        else:
            # Convert back to hex (makes all chars readable)
            byte = byte.hex()
            # Removes everything but the address
            byte = byte[20:-4]
            # Converts the hex string to bytes
            byte = bytes.fromhex(byte)
            # Formats byte to ASCII
            byte.decode("ASCII")
            # Converts byte to string
            byte = str(byte, encoding="ascii")
            for i in range(int(byte[8:12])):
                # Prints the address that was called
                print(
                    f"{self.addresses[byte[0:2]][list(self.addresses[byte[0:2]])[list(self.addresses[byte[0:2]]).index(byte[2:6])+i]]} set"
                )

    async def variable_area_read(self, command: str) -> dict:
        """Reads set values.
        
        Args:
            command (str): The desired variable
        
        Returns:
            dict: Variable:Value pair
        """
        command_data = []
        # Convert every character of the command to a byte
        for i, c in enumerate(command):
            command_data.append(c)  # Add each byte to the command_data list
        # The byte lists tracks the characters in the command
        byte_list = (
            ["\x30", "\x31", "\x30", "\x31"]  # MRC  # MRC  # SRC  # SRC
            + command_data  # command
            + ["\x30", "\x30"]  # Bit Position  # Bit Position
        )
        # Reads 1 element per call
        no_elements = ["\x30", "\x30", "\x30", "\x31"]  # '0001'
        # Add the number of elements to the byte list
        for i, c in enumerate(no_elements):
            byte_list.append(c)
        byte_list = self.__prepend(byte_list)
        byte_list = self.__append(byte_list)
        # Convert byte list to an ascii string
        byte = bytes("".join(byte_list), "ascii")
        # Compute and append the bcc
        byte += bytes([self.__bcc_calc(byte_list)])
        # Writes the command and reads the response
        ret = await self._device._write_readline(byte)
        # Converts the response to a hex string
        ret = ret.hex()
        # Checks for an error
        self.__end_code(ret)
        # Creates an empty dictionary for displaying the result
        print_dict = {}
        # Checks response code, '0000' is 'Normal Completion'
        if ret[23] != "0" or ret[25] != "0" or ret[27] != "0" or ret[29] != "0":
            print("Error occured")
            if ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "1":
                print("Command length too long")  # '1001'
            elif (
                ret[23] == "1" and ret[25] == "0" and ret[27] == "0" and ret[29] == "2"
            ):
                print("Command length too short")  # '1002'
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "1"
            ):
                print("Area Type Error")  # '1101'
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "B"
            ):
                print("Response length too long")  # '110B'
            elif (
                ret[23] == "1" and ret[25] == "1" and ret[27] == "0" and ret[29] == "0"
            ):
                print("Parameter error")  # '1100'
            elif (
                ret[23] == "2" and ret[25] == "2" and ret[27] == "0" and ret[29] == "3"
            ):
                print("Operation error")  # '2203'
            else:
                print("Unknown Error")  # Any other code
        else:
            # Removes everything but the set values from the response
            ret = ret[30:-4]
            # Convert back to hex (makes all chars readable)
            byte = byte.hex()
            # Removes everything but the address
            byte = byte[20:-4]
            # Converts the hex string to bytes
            byte = bytes.fromhex(byte)
            # Formats byte to ASCII
            byte.decode("ASCII")
            # Converts byte to string
            byte = str(byte, encoding="ascii")
            # For each element in response (should be one)
            for i in range(int(byte[8:12])):  # 8:12 should be 0001
                if byte[0:1] == "C":  # The 8 bit case
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
        return print_dict  # returns the dictionary with the address: value pairs

    # This has the right code, but I don't think it recieves the response and translates it back correctly
    # Did we just decde we didn't need it?
    # I haven't been able to test it, I can't get the device to respond (wrong port?)
    async def controller_status_read(self) -> str:
        """Reads the operating and error status.
        
        Returns:
            str: Response from device
        """
        byte_list = ["\x30", "\x36", "\x30", "\x31"]
        byte_list = self.__prepend(byte_list)
        byte_list = self.__append(byte_list)
        byte = bytes("".join(byte_list), "ascii")
        byte += bytes([self.__bcc_calc(byte_list)])
        ret = await self._device._write_readall(byte.decode("ascii"))
        return ret

    async def echo_back_test(self):
        """Performs an echo back test.

        This was used for debugging and relies on input statements.
        """
        test_input = int(input("Enter test data (0-200) >"))
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

    async def get(self, comm: list) -> dict:
        """Gets the current value of the device.
        
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

    async def set(self, comm: str, val: float) -> None:
        """Sets value of comm to val.
        
        Args:
            comm (str): Command to change
            val (float): New value for comm
        """
        # Search through addresses to find the address for the comm
        for var_type, dict in self.addresses.items():
            for add, command in dict.items():
                if comm == command:
                    comm_add = var_type + add
        await self.variable_area_write(comm_add, val)  # Sets the value
        return
