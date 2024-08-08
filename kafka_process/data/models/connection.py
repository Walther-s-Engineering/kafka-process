import typing as t

from pydantic.fields import Field, Required
from tricky.typing import Bool, Integer, String

from . import FrozenBaseModel


class ConnectionSettings(FrozenBaseModel):
    class Config:
        allow_population_by_field_name = True

    bootstrap_servers: String = Field(Required, alias="bootstrap.servers")
    username: String = Field(Required, alias="sasl.username")
    password: String = Field(Required, alias="sasl.password")
    group: String = Field(Required, alias="group.id")

    sasl_mechanism: String = Field(Required, alias="sasl.mechanism")
    sasl_protocol: String = Field(Required, alias="security.protocol")

    max_poll_interval_ms: Integer = Field(alias="max.poll.interval.ms")
    session_timeout_ms: Integer = Field(alias="session.timeout.ms")

    auto_offset_reset: String = Field(Required, alias="auto.offset.reset")
    enable_auto_commit: Bool = Field(False, alias="enable.auto.commit")

    def dict(self, *args: t.Any, **kwargs: t.Any) -> t.Dict[String, t.Any]:
        kwargs.pop("by_alias", None)
        return super().dict(*args, by_alias=True, **kwargs)
