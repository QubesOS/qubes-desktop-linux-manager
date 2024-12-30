import xml.dom

from typing import Any, Optional, Union

_basic_type = Union[int, float, bool, str]

class Node(xml.dom.Node):
    nodeName = ...  # type: str

    def getElementsByTagName(self, name: str) -> list[Element]: ...
    def getAttribute(self, attname: str) -> _basic_type: ...

class DocumentLS(object): ...
class Element(Node): ...

NodeList = list[Element]

class Document(Node, DocumentLS):
    childNodes = ...  # type:  NodeList

def parseString(string: str, parser: Optional[Any] = ...) -> Document: ...
