from typing import Iterable, Optional, Any, Callable

class EntryPoint(object):
    def load(
        self, require: bool = ..., *args: Any, **kwargs: Any
    ) -> Callable: ...

def iter_entry_points(
    group: str, name: Optional[str] = ...
) -> Iterable[EntryPoint]: ...
