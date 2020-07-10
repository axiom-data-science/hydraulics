import base64
import datetime
import io
import json
import os
import requests
from collections import namedtuple
from urllib.parse import urlparse

import faust
import numpy as np
import keras_preprocessing.image as keras_img

from avro import schema
from confluent_kafka import avro
from confluent_kafka.avro import AvroProducer
from confluent_kafka.avro.cached_schema_registry_client import CachedSchemaRegistryClient
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer

from biovolume import calc_biovolume
from blob import Blob, BlobConfig


config_path = os.environ.get('IFCB_STREAM_APP_CONFIG', 'config.json')
with open(config_path) as config_file:
    config = json.load(config_file)

Stats = namedtuple(
    'Stats',
    ['time', 'ifcb_id', 'roi', 'name', 'classifier', 'prob', 'classification_time', 'biovolume', 'carbon', 'hab']
)
ClassifierStats = namedtuple(
    'ClassifierStats',
    ['sample_name', 'prob', 'classifier', 'classification_time']
)

schema_config = {
    'url': config['schema.registry.url'],
    'ssl.ca.location': None
}
# need to use CachedSchemaRegistryClient to get schema
# - need to copy config because it is consumed when used in CachedSchemaRegistryClient
schema_config_copy = schema_config.copy()
cached_schema_client = CachedSchemaRegistryClient(schema_config)
key_schema = str(cached_schema_client.get_latest_schema('ifcb-stats-key')[1])
value_schema = str(cached_schema_client.get_latest_schema('ifcb-stats-value')[1])

key_schema = avro.loads(key_schema)
value_schema = avro.loads(value_schema)
producer = AvroProducer({
    'bootstrap.servers': config['bootstrap.servers'],
    'schema.registry.url': config['schema.registry.url']
    },
    default_key_schema=key_schema,
    default_value_schema=value_schema
)


app = faust.App(
    config['app_name'],
    broker=config['broker'],
    topic_partitions=config['topic_partitions'],
    store='rocksdb://',
    consumer_auto_offset_reset='earliest',
    version=1
)

image_topic = app.topic(config['image_topic'])
stats_topic = app.topic(config['stats_topic'])
classifier_stats_table = app.Table('ifcb-classifier-stats', default=ClassifierStats)

diatoms = config['diatoms']
class_names = config['class_names']
hab_species = config['hab_species']


def publish_stats(feature_key, image, classifier_stats, blob_config=BlobConfig()):
    """Calculate biovolume, carbon, hab, and publish to Kafka"""
    # calculate biovolume
    # - scale biovolume for 3d (from ifcb-analysis)
    blob = Blob(image, blob_config)
    biovolume = calc_biovolume(blob)
    mu = 1/3.4
    biovolume = biovolume * mu ** 3
    carbon = calc_carbon(classifier_stats[0], biovolume)
    hab = classifier_stats[0] in hab_species

    time, ifcb_id, roi = feature_key.split('_')
    roi = int(roi)
    timestamp = int(datetime.datetime.strptime(time[1:], '%Y%m%dT%H%M%S').timestamp())
    stats = Stats(
        timestamp,
        ifcb_id,
        roi,
        classifier_stats[0],
        classifier_stats[2],
        classifier_stats[1],
        classifier_stats[3],
        biovolume,
        carbon,
        hab
    )

    # send to topic with Avro schema
    producer.poll(0)
    producer.produce(
        topic=config['stats_topic'],
        key={
            'pid': f"{time}_{ifcb_id}",
            'roi': int(roi)
        },
        value=stats._asdict()
    )
    producer.flush()


@app.agent(image_topic)
async def classify(images, url=config['tensorflow_url'], target_size=(224, 224)):
    async for image in images:
        # decode binary blob to png file then resize and normalize
        image_str = base64.b64decode(image['image'])
        image_file = io.BytesIO(image_str)
        img = keras_img.img_to_array(
            keras_img.load_img(image_file, target_size=target_size)
        )
        img /= 255

        # create payload and send to TF RESTful API
        headers = {"content-type": "application/json"}
        data = json.dumps({'instances': [img.tolist()]})
        result = requests.post(url, headers=headers, data=data)

        # save the probabilities for each class (1d ndarray)
        probs = result.json()['predictions'][0][:]

        # feature_key is roi
        time = datetime.datetime.fromtimestamp(image['datetime'])
        feature_key = f"{time:D%Y%m%dT%H%M%S}_{image['ifcb_id']}_{image['roi']:05}"

        print(f'processing {feature_key}')

        # update table if current prob is greater than what is already in the table
        prob = np.nanmax(probs)
        if feature_key not in classifier_stats_table or prob > classifier_stats_table[feature_key].prob:
            name = class_names[np.argmax(probs)]
            classifier, version = get_classifier(url)
            classifier_version = f'{classifier}:{version}'
            classifier_stats_table[feature_key] = ClassifierStats(
                name,
                prob,
                classifier_version,
                int(datetime.datetime.utcnow().timestamp())
            )

        # send
        publish_stats(feature_key, image_str, classifier_stats_table[feature_key])


def get_classifier(url):
    """Given TF style url, return name and version"""
    parse_results = urlparse(url)
    _, version, _, name_raw = parse_results.path.split('/')
    name = name_raw.split(':')[0]

    return (name, version)


def calc_carbon(english_name, scaled_biovolume, diatom_list=diatoms):
    """Given volume in u3/cell return carbon in pg C/cell.

    $log_10(C) = log(a) + b \cdot log_10(V)$
    """
    if english_name in diatom_list:
        carbon = 10**(-0.665 + 0.939*np.log10(scaled_biovolume))
    else:
        carbon = 10**(-0.993 + 0.881*np.log10(scaled_biovolume))
    return carbon

if __name__ == '__main__':
    app.main()
