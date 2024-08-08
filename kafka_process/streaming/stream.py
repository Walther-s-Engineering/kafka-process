from __future__ import annotations

import contextlib
import threading
import typing as t
from pprint import pformat
from queue import Empty, Full, Queue

import attrs
import orjson
from confluent_kafka import Consumer, KafkaException, Message, Producer
from confluent_kafka.admin import AdminClient
from loguru._logger import Logger
from pydantic.main import BaseModel
from tricky.getters import preserve_attr
from tricky.iterables import unzip
from tricky.typing import Bool, Integer, String

from kafka_process.data.models.message import Message as MessageModel
from kafka_process.logger import logger as base_logger
from kafka_process.helpers import parsing

__all__ = ("Stream",)

_Serializer = t.TypeVar("_Serializer", bound=BaseModel)
_Message = t.TypeVar("_Message")

logger = base_logger.bind(caller="Stream")


@attrs.define
class StreamMessagesIterator(t.Generic[_Message]):
    stream: Stream
    filter: t.Callable[[MessageModel], Bool]

    def __iter__(self) -> StreamMessagesIterator:
        if not self.stream.started.is_set():
            raise RuntimeError("Stream is not started")
        return self

    def __next__(self) -> MessageModel:
        message: Message = self.stream.__next__()
        if self.filter(message) is False:
            raise StopIteration
        return message


@attrs.define
class Stream:
    name: String

    source_topics: t.List[String]
    target_topics: t.List[String]

    consumer_settings: t.Optional[KafkaSettings]
    producer_settings: t.Optional[KafkaSettings]

    queue_size: Integer

    admin: t.Optional[AdminClient] = attrs.field(default=None)
    consumer: t.Optional[Consumer] = attrs.field(default=None)
    producer: t.Optional[Producer] = attrs.field(default=None)

    enable_commit: Bool = False
    filters: t.List[t.Callable[..., Bool]] = []
    serializer: t.Optional[_Serializer] = None  # type: ignore[valid-type]

    poll_timeout: Integer = 3
    messages_queue: Queue[Message] = attrs.field(init=False)
    messages_count: Integer = 0
    commit_unprocessed: Bool = False

    started: threading.Event = attrs.field(init=False)
    stopped: threading.Event = attrs.field(init=False)
    shutdown: threading.Event = attrs.field(init=False)

    logger: Logger = attrs.field(init=False)

    _lock: threading.Lock = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        self.logger = base_logger.bind(caller=self.name)

        self.messages_queue = Queue(maxsize=self.queue_size)
        if self.consumer_settings is not None:
            self._setup_admin(
                self.consumer_settings.dict(by_alias=True),
            )
            self._setup_consumer(
                self.consumer_settings.dict(by_alias=True),
            )
        if self.producer_settings is not None:
            self._setup_producer(
                self.producer_settings.dict(by_alias=True),
            )
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.shutdown = threading.Event()
        self._lock = threading.Lock()

    @property
    def qsize(self) -> Integer:
        return self.messages_queue.qsize()

    @staticmethod
    def _setup_connection(
        class_: t.Type[Consumer] | t.Type[Producer] | t.Type[AdminClient],
        options: t.Dict[String, t.Any],
    ) -> Consumer | Producer | AdminClient:
        return class_(options)

    def _setup_admin(self, options: t.Dict[String, t.Any]) -> None:
        unable_options = ("group.id", "session.timeout.ms", "max.poll.interval.ms")
        for option in unable_options:
            if options.get(option) is not None:
                del options[option]
        self.admin = self._setup_connection(AdminClient, options)
        self.logger.info(
            f"Admin client was successfully set at '{options['bootstrap.servers']}'",
        )

    def _setup_consumer(self, options: t.Dict[String, t.Any]) -> None:
        if group_id := options.get("group.id", "kafka-pourer-consumer"):
            options["group.id"] = group_id
        self.consumer = self._setup_connection(Consumer, options)
        source_topics = ", ".join(self.source_topics)
        self.logger.info(f"Consumer was successfully set to source topics: {source_topics}")

    def _setup_producer(self, options: t.Dict[String, t.Any]) -> None:
        self.producer = self._setup_connection(Producer, options)
        target_topics = ", ".join(self.target_topics)
        self.logger.info(f"Producer was successfully set to target topics: {target_topics}")

    def pause(self) -> threading.Lock:
        if not self.stopped.is_set() and not self.shutdown.is_set():
            self.logger.warning("Stream manually paused until lock release")
            return self._lock
        raise SystemExit(1) from RuntimeError("Cannot suspend a stopped or disabled thread")

    def commit(self) -> None:
        if self.enable_commit:
            self.consumer.commit()  # type: ignore[union-attr]
        self.messages_count += 1

    def subscribe(self, topics: t.Optional[t.List[String]] = None) -> None:
        if self.consumer is not None:
            if topics is not None:
                self.consumer.subscribe(topics)
            self.consumer.subscribe(self.source_topics)
        else:
            raise RuntimeError("Consumer is not instantiated for this stream instance")

    def poll_loop(self) -> None:  # noqa: C901
        self.logger.debug(
            f"Starting poll loop on kafka '{self.consumer_settings.bootstrap_servers}'",  # type: ignore[union-attr]
        )
        self.stopped.clear()
        self.shutdown.clear()

        if self.consumer is None:
            self.stopped.set()
            raise ValueError("Consumer must be set before start polling loop")
        try:
            self.consumer.subscribe(self.source_topics)
            joined_topics = ", ".join(
                set(unzip(self.source_topics, self.target_topics)),
            )
            self.logger.info(f"Subscribed to topics: {joined_topics}")
            self.started.set()
            is_started = False

            while not self.stopped.is_set() and self.started.is_set():
                if self._lock.locked():
                    continue

                if is_started is False:
                    self.logger.info(
                        "Successfully started poll loop on topics: "
                        f"{', '.join(self.source_topics)}"
                    )
                    is_started = True

                message = self.consumer.poll(self.poll_timeout)
                if self.is_heart_beat(message):
                    self.logger.trace(f"Heartbeat at '{joined_topics}' . . .")
                    continue

                if self.is_error(message):
                    logger.warning("Ignoring error and proceeding listening stream")
                    continue

                try:
                    is_success_filter = self.apply_filters(message)
                    if is_success_filter is None:
                        self.messages_queue.put(message)
                        self.commit()

                    if is_success_filter is True:
                        self.messages_queue.put(message)
                        self.commit()
                    else:
                        if self.commit_unprocessed:
                            self.commit()
                    continue
                except Full:
                    self.logger.error("Messages queue is exhausted")
                    self.logger.exception("Queue full exception:")
                    continue
            else:
                self.logger.error("Poll loop is unable to start or stopped before shutdown")
                self.started.clear()
                self.stopped.set()
                raise SystemExit
        except Exception:
            self.stopped.set()
            raise

    def produce(
        self,
        topic: String,
        value: t.Union[t.List, t.Dict, t.Any],
        headers: t.Optional[t.Dict] = None,
        on_delivery: t.Optional[t.Callable] = None,
    ) -> None:
        if self.producer is None:
            self.stopped.set()
            raise ValueError("Producer must be set before start polling loop")
        self.producer.produce(
            topic,
            value=orjson.dumps(value),
            headers=headers,
            on_delivery=on_delivery,
        )
        self.producer.flush()

    def stop(self) -> None:
        joined_topics = ", ".join(
            set(unzip(self.source_topics, self.target_topics)),
        )
        self.logger.warning(f"Stopping stream running at '{joined_topics}'")
        self.started.clear()
        self.stopped.set()

        with contextlib.suppress(KafkaException, RuntimeError):
            self.consumer.unsubscribe()  # type: ignore[union-attr]
        self.consumer.close()  # type: ignore[union-attr]

        with contextlib.suppress(AttributeError):
            del self.admin

        with contextlib.suppress(AttributeError):
            del self.producer

        locks = [self.messages_queue.mutex, self.messages_queue.all_tasks_done]
        for lock in locks:
            try:
                lock.release()  # type: ignore[attr-defined]
            except RuntimeError:
                self.logger.warning(f"Lock '{lock}' already released")
        self.shutdown.set()
        self.logger.info(f"Stream at '{joined_topics}' successfully stopped!")

    def serialize_message(self, message: Message):
        headers: t.Dict[String, String] = dict()
        if message.headers() is not None:
            headers: t.Dict[String, String] = parsing.parse_message_headers(message.headers())  # type: ignore[no-redef]

        payload = t.cast(t.Dict, orjson.loads(message.value().decode()))

        if self.serializer is not None:
            payload = self.serializer.parse_obj(payload)

        try:
            return MessageModel(
                headers=headers,
                payload=payload,
            )
        except Exception:
            self.logger.exception(
                "Failed to parse message:"
                "\n\theaders: {headers}"
                "\n\tpayload: {payload}".format(
                    headers=pformat(headers),
                    payload=pformat(payload),
                ),
            )

    def filter(
        self,
        predicate: t.Callable[..., Bool],
    ) -> StreamMessagesIterator[Message]:
        if not self.started.is_set():
            self.logger.warning("Stream is not started waiting for it 30 seconds")
        self.started.wait(timeout=5)
        return StreamMessagesIterator(self, predicate)

    def batch(self, limit: t.Optional[Integer] = None) -> t.List[MessageModel]:
        messages: t.List[MessageModel] = []
        if limit is not None:
            if limit >= self.qsize:
                limit = self.qsize
        else:
            limit = self.qsize
        with contextlib.suppress(StopIteration, Empty):
            for _ in range(limit):
                messages.append(
                    self.serialize_message(
                        self.messages_queue.get_nowait(),
                    ),
                )
        return messages

    def apply_filters(self, message: Message) -> t.Optional[Bool]:
        if self.filters:
            is_success_filter = all(
                [message_filter(self, message) is True for message_filter in self.filters],
            )
            return is_success_filter
        return None

    def is_heart_beat(self, message: t.Optional[Message]) -> Bool:
        if message is None:
            return True
        return False

    def is_error(self, message: Message) -> Bool:
        if message.error():
            self.logger.error(
                "Occurred unhandled error while processing kafka message. "
                "At host: {}\n"
                "Detail: {}\n",
                ", ".join(
                    {
                        preserve_attr(self.consumer_settings, "bootstrap_servers", ""),
                        preserve_attr(self.producer_settings, "bootstrap_servers", ""),
                    },
                ),
                message.error(),
            )
            topics = ", ".join(f'"{topic}"' for topic in self.source_topics)
            self.logger.warning(
                f"Due the kafka-connection error consumer will be resubscribed to: {topics}",
            )
            self.consumer.subscribe(self.source_topics)  # type: ignore[union-attr]
            return True
        return False

    def __iter__(self) -> Stream:
        if self.stopped.is_set():
            raise RuntimeError("Stream is stopped")
        if self.shutdown.is_set():
            raise RuntimeError("Stream is shutdown")
        return self

    def __next__(self) -> t.Optional[MessageModel]:
        try:
            if self.stopped.is_set():
                self.started.clear()
                raise StopIteration("Stream is stopped")
            if self.shutdown.is_set():
                self.started.clear()
                self.stopped.clear()
                raise StopIteration("Stream is shutdown")

            if self.consumer is None:
                raise RuntimeError("Consumer is not instantiated for this stream instance")

            message: t.Optional[Message] = self.consumer.poll()

            if self.is_heart_beat(message):
                joined_topics = ", ".join(
                    set(unzip(self.source_topics, self.target_topics)),
                )
                self.logger.trace(f"Heartbeat at '{joined_topics}' . . .")
                return None

            if self.is_error(message):
                logger.warning("Ignoring error and proceeding listening stream")
                return None
            return self.serialize_message(message)
        except KeyboardInterrupt:
            self.stop()
            raise
