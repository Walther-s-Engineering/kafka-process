import typing as t

from tricky.typing import Bytes, String

from kafka_process.logger import logger as base_logger

logger = base_logger.bind(caller="parsing.py")


def parse_message_headers(
    raw_headers: t.List[t.Tuple[String, Bytes]],
) -> t.Dict[String, String]:
    try:
        headers = list(
            map(
                lambda items: tuple(
                    item.decode() if hasattr(item, "decode") else item for item in (items or {})
                ),
                raw_headers,
            ),
        )
        headers = t.cast(t.List[t.Tuple[String, String]], headers)
        return dict(headers)

    except (ValueError, TypeError, AttributeError):
        logger.exception("Failed to parse headers of message!")
        return dict()
