#!python
import argparse
import json
import logging
from pathlib import Path

from avro import schema
from confluent_kafka.avro import CachedSchemaRegistryClient
from confluent_kafka.avro import error as avro_error


# Monkey patch to get hashable avro schemas
# https://issues.apache.org/jira/browse/AVRO-1737
# https://github.com/confluentinc/confluent-kafka-python/issues/122
def hash_func(self):
    return hash(str(self))
schema.EnumSchema.__hash__ = hash_func
schema.RecordSchema.__hash__ = hash_func
schema.PrimitiveSchema.__hash__ = hash_func
schema.ArraySchema.__hash__ = hash_func
schema.FixedSchema.__hash__ = hash_func
schema.MapSchema.__hash__ = hash_func
schema.UnionSchema.__hash__ = hash_func


def update(topic, schema_config, force=False):
    """Given a topic, update (or create) a schema"""
    client = CachedSchemaRegistryClient(schema_config)

    if topic == 'all':
        schema_files = Path(__file__).parent.glob('**/*.avsc')
    else:
        schema_files = Path(__file__).parent.glob(f'**/{topic}-*.avsc')

    for schema_file in schema_files:
        with open(schema_file) as f:
            schema_str = f.read()
        schema_dict = json.loads(schema_str)
        avro_schema = schema.Parse(schema_str)

        subject = schema_dict['namespace'].replace('.', '-') + '-' + schema_dict['name']
        if force:
            client.update_compatibility('NONE', subject=subject)
        else:
            client.update_compatibility('BACKWARD', subject=subject)

        try:
            schema_id = client.register(subject, avro_schema)
            log.info(f'Added/updated {schema_file}\t Schema ID {schema_id}')
        except avro_error.ClientError as error:
            log.error(f'Error adding/updating {schema_file}: {error.message}')


if __name__ == '__main__':
    log = logging.getLogger('avro-schemas')
    log.setLevel(logging.INFO)
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)-15s  %(levelname)-8s %(message)s"))
    log.addHandler(sh)
    log.propagate = False

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'schema',
        type=str,
        help='Name of schema to update.  "all" to add/update all schemas'
    )
    parser.add_argument(
        'url',
        type=str,
        help='URL to a schema registry'
    )
    parser.add_argument(
        '--force',
        dest='force',
        action='store_true',
        help='Force upgrade the schemas even if not backwards compatible (sets compability to "NONE")'
    )

    args = parser.parse_args()
    schema_config = {
        'url': args.url,
        'ssl.ca.location': None
    }
    if args.force:
        log.info(f'Forcing adding/updating of {args.schema} schema(s) registered on {args.url}')
    else:
        log.info(f'Adding/updating {args.schema} schema(s) registered on {args.url}')
    update(args.schema, schema_config, args.force)
