import typing as t

from pydantic.main import BaseModel
from pydantic.env_settings import BaseSettings
from tricky.typing import String


_alias_upper = lambda field: field.upper()  # noqa: E731


class LoggingSettings(BaseModel):
    class Config:
        allow_population_by_field_name = True
        alias_generator = _alias_upper

    LEVEL: String = "ERROR"
    FORMAT: String = "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>:<green>{extra[caller]}</green>"
    EXTRA_KEY: String = "caller"
    EXTRA_VALUES: String = ""


class ModuleSettings(BaseSettings):
    class Config:
        env_prefix = 'KAFKA_PROCESS_'
        env_nested_delimiter = "__"
        allow_population_by_field_name = True
        alias_generator = _alias_upper

    LOGGING_SETTINGS: t.Optional[LoggingSettings]


settings = ModuleSettings()
logging_settings = settings.LOGGING_SETTINGS
