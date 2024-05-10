"""DAQ Class for managing OMRON devices. Accessible to external API and internal logging module.

Author: Grayson Bellamy
Date: 2024-01-07
"""

import device
from trio import run


class DAQ:
    """Class for managing OMRON devices. Accessible to external API and internal logging module. Wraps and allows communication with inidividual or all devices through wrapper class."""

    def __init__(self) -> None:
        """Initializes the DAQ.

        TODO: Pass dictionary of names and addresses to initialize devices. Same async issue.

        """
        global dev_list
        dev_list = {}

        """
        for name in devs:
            dev = device.new_device(devs[name])
            dev_list.update({name: dev})
        """
        return

    @classmethod
    async def init(cls, devs: dict[str, str] = "") -> "DAQ":
        """Initializes the DAQ.

        Example:
            Daq = run(DAQ.init, {'A':'/dev/ttyUSB6', 'B':'/dev/ttyUSB7'})

        Args:
            devs (dict[str, str]): The dictionary of devices to add. Name:Port

        Returns:
            DAQ: The DAQ object.
        """
        daq = cls()
        await daq.add_device(devs)
        return daq

    async def add_device(self, devs: dict[str, str] = "") -> None:
        """Creates and initializes the devices.

        Args:
            devs (dict[str, str]): The dictionary of devices to add. Name:Port
        """
        if devs:
            if isinstance(devs, str):
                devs = devs.split()
                # This works if the string is the format "Name Port"
                devs = {devs[0]: devs[1]}
            for name in devs:
                dev = await device.Omron.new_device(devs[name])
                dev_list.update({name: dev})
        return

    async def remove_device(self, name: list[str]) -> None:
        """Creates and initializes the devices.

        Args:
            name (list[str]): The list of devices to remove.
        """
        for n in name:
            await dev_list[n]._device.close()
            del dev_list[n]
        return

    async def dev_list(self) -> dict[str, device.Omron]:
        """Displays the list of devices.

        Returns:
            dict[str, device.Omron]: The list of devices and their objects.
        """
        return dev_list

    async def get(
        self, val: list[str] = "", id: list[str] = ""
    ) -> dict[str, dict[str, str | float]]:
        """Gets the data from the device.

        If id not specified, returns data from all devices.

        Example:
            df = run(Daq.get, ["Version", "Communications Main Setting 1", "Communications Parity"], ['A', 'B'])
            df = run(Daq.get, ["Version", "Communications Main Setting 1", "Communications Parity"])
            df = run(Daq.get, ["Version", "Communications Main Setting 1", "Communications Parity"], 'B')
            df = run(Daq.get, "Version")

        Args:
           val (list[str]): The values to get from the device.
           id (list[str]): The IDs of the devices to read from. If not specified, returns data from all devices.

        Returns:
            dict[str, dict[str, str | float]]: The dictionary of devices with the data for each value.
        """
        ret_dict = {}
        if isinstance(val, str):
            val = [val]
        if not id:
            for dev in dev_list:
                ret_dict.update({dev: await dev_list[dev].get(val)})
        if isinstance(id, str):
            id = id.split()
        for i in id:
            ret_dict.update({i: await dev_list[i].get(val)})
        return ret_dict

    async def set(
        self, command: dict[str, str | float], id: list[str] = ""
    ) -> dict[str, None]:
        """Sets the data of the device.

        Example:
            df = run(Daq.set, {"Communications Parity": "Even", 'Output Upper Limit': 100})
            df = run(Daq.set, {"Communications Parity": "Even", 'Output Upper Limit': 100}, ['A', 'B'])
            df = run(Daq.set, {"Communications Parity": "Even", 'Output Upper Limit': 100}, ["B"])

        Args:
           command (dict[str, str | float]): The commands and their relevant parameters to send to the device.
           id (list[str]): The IDs of the devices to read from. If not specified, returns data from all devices.

        Returns:
            dict[str, None]: The dictionary of devices changed.
        """
        ret_dict = {}
        if isinstance(command, str):
            command = [command]
        if not id:
            for dev in dev_list:
                ret_dict.update({dev: await dev_list[dev].set(command)})
        if isinstance(id, str):
            id = id.split()
        for i in id:
            ret_dict.update({i: await dev_list[i].set(command)})
        return ret_dict

    async def heat(self, setpoint: float, id: str = "") -> dict[str, None]:
        """Convenience: Sets the heater setpoint.

        Example:
            df = run(Daq.heat, 0.0, ['A', 'B'])
            df = run(Daq.heat, 0.0)

        Args:
            setpoint (float): The desired setpoint

        Returns:
            dict[str, None]: The dictionary of devices changed.
        """
        ret_dict = {}
        if not id:
            for dev in dev_list:
                ret_dict.update(
                    {
                        dev: await dev_list[dev].set(
                            {"Communications Main Setting 1": setpoint}
                        )
                    }
                )
        if isinstance(id, str):
            id = id.split()
        for i in id:
            ret_dict.update(
                {i: await dev_list[i].set({"Communications Main Setting 1": setpoint})}
            )
        return ret_dict

    async def monitors(self, id: str = "") -> dict[str, dict[str, float]]:
        """Convenience: Gets the current monitor values.

        Example:
            df = run(Daq.monitors, ['A', 'B'])
            df = run(Daq.monitors)

        Args:
            setpoint (float): The desired setpoint

        Returns:
            dict[str, dict[str, float]]: The dictionary of devices with the communication main settings for each.
        """
        ret_dict = {}
        if not id:
            for dev in dev_list:
                ret_dict.update(
                    {dev: await dev_list[dev]._variable_area_read("810000", 8)}
                )
        if isinstance(id, str):
            id = id.split()
        for i in id:
            ret_dict.update({i: await dev_list[i]._variable_area_read("810000", 8)})
        return ret_dict


class DAQLogging:
    """Class for logging the data from OMRON devices. Creates and saves file to disk with given acquisition rate. Only used for standalone logging. Use external API for use as plugin."""

    def __init__(self, config: dict) -> None:
        """Initializes the Logging module. Creates and saves file to disk with given acquisition rate.

        Parameters
        ----------
        config : dict
            The configuration dictionary. {Name : port}
        """
        pass
