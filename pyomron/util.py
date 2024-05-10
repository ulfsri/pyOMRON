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
import daq


def gas_correction():
    """Calculates the gas correction factor for the OMRON device.

    Returns:
    -------
    float
        The gas correction factor.
    """
    pass


async def find_devices() -> dict[str, str]:
    """Finds all connected OMRON devices.

    Find all available serial ports using the `ls` command
    Iterate through all possible baud rates

    If there is an OMRON device on that port (copy code form new_device that checks )
        get what device is
    add to dictionary with port name and type of device on port (if no device, don't add to dictionary)
    return dictionary


    Returns:
        dict[str, str]: A dictionary of all connected OMRON devices. Port:DeviceType
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


async def is_omron_device(port: str, **kwargs: Any) -> bool:
    """Check if the given port is an OMRON device.

    Parameters:
        port(str): The name of the serial port.

    Returns:
        bool: True if the port is an OMRON device, False otherwise.
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


def get_device_type(port) -> dict[str, str]:
    """Get the device type for the given port.

    Parameters:
    port(str): The name of the serial port.

    Returns:
        dict[str, str]: A dictionary containing the port name and the type of device on the port.
    """
    # Implement the logic to get the device information
    # You can use any method that suits your needs
    pass


async def diagnose():
    """Run various functions to ensure the device is functioning properly."""
    get_code1 = "Version"
    get_code2 = "Internal Duty Setting"
    set_code = "Output Upper Limit"
    devs = await find_devices()
    print(f"Devices: {devs}")
    Daq = await daq.DAQ.init({"A": list(devs.keys())[0]})
    print(f"Initiate DAQ with A: {await Daq.dev_list()}")
    await Daq.add_device({"B": list(devs.keys())[1]})
    print(f"Add device B: {await Daq.dev_list()}")
    print(f"Get data (list): {await Daq.get([get_code1, get_code2])}")
    temp = await Daq.get(set_code, "B")
    print(f"Get Data (id, no list): Temp = {temp}")
    await Daq.remove_device(["A"])
    print(f"Remove device A: {await Daq.dev_list()}")
    print(f"Set data (with id).")
    await Daq.set({set_code: (temp["B"][set_code] - 1)}, "B")
    print(f"Get data: {await Daq.get([set_code])}")
    print(f"Set data (without id).")
    await Daq.set({set_code: temp["B"][set_code]})
    print(f"Get data: {await Daq.get([set_code])}")
    await Daq.add_device({"C": list(devs.keys())[0]})
    print(f"Add device C: {await Daq.dev_list()}")
    print(f"Convenience Function: {await Daq.monitors()}")
