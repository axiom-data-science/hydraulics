from confluent_kafka import Message


def delivery_report(err: str, msg: Message) -> None:
    """Callback for Kafka message delivery"""
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to topic: {msg.topic()}, partition: {msg.partition()}, offset: {msg.offset()}')
