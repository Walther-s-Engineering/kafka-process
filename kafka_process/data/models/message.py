import typing as t

from tricky.typing import Integer, String

from . import FrozenBaseModel

__all__ = ("Message",)


class Message(FrozenBaseModel):
    headers: t.Dict[String, t.Any]
    payload: t.Union[
        t.Dict,
        t.List,
        t.Tuple,
    ]
    topic: String
    partition: t.Optional[Integer]
    offset: t.Optional[Integer]
