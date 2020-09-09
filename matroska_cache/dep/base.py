from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class DependencyBase(ABC):
    # Performance
    __slots__ = ()

    # key() prefix. Used for overrides in subclasses
    PREFIX = '?'

    @abstractmethod
    def key(self) -> str:
        """ Get string representation of this dependency """
