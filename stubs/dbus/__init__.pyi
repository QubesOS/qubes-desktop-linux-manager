# Stubs for dbus

import dbus.mainloop
import dbus.proxies
import dbus._dbus
from typing import Optional, Union, Callable

class Interface(object):
    def __init__(
        self,
        object: Union[dbus.proxies.ProxyObject, Interface],
        dbus_interface: str,
    ) -> None: ...
    def get_dbus_method(
        self, member: str, dbus_interface: Optional[str] = ...
    ) -> Callable: ...

class Bus(dbus.bus.BusConnection):
    def __new__(
        cls,
        bus_type: Optional[int],
        private: Optional[bool] = ...,
        mainloop: Optional[dbus.mainloop.NativeMainLoop] = ...,
    ) -> dbus.bus.BusConnection: ...

class SessionBus(Bus):
    def __new__(
        cls,
        private: Optional[bool] = ...,
        mainloop: Optional[dbus.mainloop.NativeMainLoop] = ...,
    ) -> Bus: ...

class String(str): ...
class Boolean(int): ...
class Int32(int): ...
class Array(list): ...
class Dictionary(dict): ...
class ObjectPath(str): ...

# vim: syntax=python
