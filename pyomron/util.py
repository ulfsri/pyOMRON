"""Utilities for manipulating data from OMRON devices.

Author: Grayson Bellamy
Date: 2024-01-07
"""

import glob
from comm import SerialDevice
from device import Omron
from trio import run
import trio
import re
from typing import Any


def gas_correction():
    """Calculates the gas correction factor for the OMRON device.

    Returns:
    -------
    float
        The gas correction factor.
    """
    pass


async def find_devices():
    """Finds all connected OMRON devices.

    Find all available serial ports using the `ls` command
    Iterate through all possible baud rates

    If there is an OMRON device on that port (copy code form new_device that checks )
        get what device is
    add to dictionary with port name and type of device on port (if no device, don't add to dictionary)
    return dictionary


    Returns:
    -------
    list
        A list of all connected OMRON devices.
    """
    # Get the list of available serial ports
    result = glob.glob("/dev/ttyUSB*")
    # result = result[:4] + result[6:]

    # Iterate through the output and check for OMRON devices
    devices = {}
    for port in result:
        # Check if the port is an OMRON device
        dev = await is_omron_device(port)
        if dev:
            devices.update({port: dev[1]})
    return devices


async def is_omron_device(port, id: str = "A", **kwargs: Any):
    """Check if the given port is an OMRON device.

    Parameters:
    ----------
    port : str
        The name of the serial port.

    Returns:
    -------
    bool
        True if the port is an OMRON device, False otherwise.
    """
    if port.startswith("/dev/"):
        device = SerialDevice(port, **kwargs)
    byte_list = [
        "\x30",
        "\x35",
        "\x30",
        "\x33",
    ]  # Command for controller attribute read
    byte_list = await Omron._prepend(byte_list)
    byte_list = await Omron._append(byte_list)
    byte = bytes("".join(byte_list), "ascii")
    byte += bytes([await Omron._bcc_calc(byte_list)])
    resp = await device._write_readline(byte)
    try:
        await Omron._check_response_code(resp)
    except ValueError:
        return False
    ret = resp[15:-6].decode("ascii")
    # Chek using is_model class to see if it matches G3PW
    if await Omron._is_model(ret):
        return (True, "OMRON")
    else:
        return False


def get_device_type(port):
    """Get the device type for the given port.

    Parameters:
    ----------
    port : str
        The name of the serial port.

    Returns:
    -------
    dict
        A dictionary containing the port name and the type of device on the port.
    """
    # Implement the logic to get the device information
    # You can use any method that suits your needs
    pass
