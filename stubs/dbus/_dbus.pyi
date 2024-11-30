from typing import Optional
import dbus
import dbus.bus
import dbus.mainloop

class SessionBus(dbus.bus.BusConnection):
    def __new__(
        cls,
        private: Optional[bool] = ...,
        mainloop: Optional[dbus.mainloop.NativeMainLoop] = ...,
    ) -> dbus.Bus: ...

# vim: syntax=python
