# Stubs for dbus.proxies
import dbus

from typing import Callable, Optional, Union

ObjectPath = Union[dbus.ObjectPath, str]

class ProxyObject(object):

    bus_name = ...  # type: str

    def __init__(
        conn: dbus.Bus = ...,
        bus_name: str = ...,
        object_path: ObjectPath = ...,
        follow_name_owner_changes: bool = ...,
        introspect: bool = ...,
        **kwargs
    ) -> None: ...
    def get_dbus_method(
        self, member: str = ..., dbus_interface: Optional[str] = ...
    ) -> Callable: ...
    def connect_to_signal(
        self,
        signal_name: str = ...,
        handler_function: Callable = ...,
        dbus_interface: Optional[str] = ...,
        **keywords
    ) -> None: ...
    def Introspect(self) -> dbus.String: ...

# vim: ft=python tw=0 syntax=python
