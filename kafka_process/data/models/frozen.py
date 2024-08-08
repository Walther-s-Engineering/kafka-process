from pydantic.config import ConfigDict
from pydantic.main import BaseModel


class FrozenBaseModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        populate_by_name=True,
    )
