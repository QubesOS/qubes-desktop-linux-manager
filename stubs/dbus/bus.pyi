import dbus.connection
import dbus.proxies
from typing import Optional

class BusConnection(dbus.connection.Connection):
    def get_object(
        self,
        bus_name: str = ...,
        object_path: str = ...,
        introspect: Optional[bool] = ...,
        follow_name_owner_changes: Optional[bool] = ...,
    ) -> dbus.proxies.ProxyObject: ...

# vim: syntax=python
