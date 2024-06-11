"""Utilities for manipulating data from OMRON devices.

Author: Grayson Bellamy
Date: 2024-01-07
"""

import glob
import re
from typing import Any

import daq
from anyio import create_task_group, run
from comm import SerialDevice
from device import Omron


def gas_correction():
    """Calculates the gas correction factor for the OMRON device.

    Returns:
    -------
    float
        The gas correction factor.
    """
    pass


async def update_dict_dev(
    devices: dict[str, Omron], port: str
) -> dict[str, dict[str, str | float]]:
    """Updates the dictionary with the new values.

    Args:
        devices (dict): The dictionary of devices.
        port (str): The name of the serial port.

    Returns:
        dict: The dictionary of devices with the updated values.
    """
    dev = await is_omron_device(port)
    if dev:
        devices.update({port: dev[1]})
    return devices


async def find_devices() -> dict[str, Omron]:
    """Finds all connected OMRON devices.

    Find all available serial ports using the `ls` command
    Iterate through all possible baud rates

    If there is an OMRON device on that port (copy code form new_device that checks )
        get what device is
    add to dictionary with port name and type of device on port (if no device, don't add to dictionary)
    return dictionary


    Returns:
        dict[str, Omron]: A dictionary of all connected OMRON devices. Port:Object
    """
    # Get the list of available serial ports
    result = glob.glob("/dev/ttyUSB*")

    # Iterate through the output and check for OMRON devices
    devices: dict[str, Omron] = {}
    async with create_task_group() as g:
        for port in result:
            g.start_soon(update_dict_dev, devices, port)
    return devices


async def is_omron_device(port: str, **kwargs: Any) -> bool | tuple[bool, Omron]:
    """Check if the given port is an OMRON device.

    Parameters:
        port(str): The name of the serial port.
        **kwargs: Any additional keyword arguments.

    Returns:
        bool: True if the port is an OMRON device, False otherwise.
        Omron: The OMRON device object.
    """
    try:
        return (True, await Omron.new_device(port, **kwargs))
    except ValueError:
        return False


async def diagnose():
    """Run various functions to ensure the device is functioning properly."""
    get_code1 = "Version"
    get_code2 = "Internal_Duty_Setting"
    set_code = "Output_Upper_Limit"
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
