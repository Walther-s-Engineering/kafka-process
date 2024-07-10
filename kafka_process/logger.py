import sys

from loguru import logger as origin_logger
from loguru._defaults import LOGURU_FORMAT

from kafka_process.config import logging_settings

__all__ = ("logger",)


def create_logger():
    origin_logger.remove(0)
    formatting = LOGURU_FORMAT.replace(
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan>",
        logging_settings.FORMAT,
    )
    origin_logger.configure(
        extra={
            logging_settings.EXTRA_KEY: logging_settings.EXTRA_VALUES,
        },
    )
    origin_logger.add(sys.stderr, format=formatting, level=logging_settings.LOGGING_LEVEL)
    return origin_logger


logger = create_logger()
