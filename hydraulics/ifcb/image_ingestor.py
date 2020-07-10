#!python
"""Ingest image data from an ifcb-dashboard to a Kafka instance"""
import base64
import datetime
import io
import json
import logging
import requests
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Union

import typer
from confluent_kafka import Message, SerializingProducer

logger = logging.getLogger(__file__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

app = typer.Typer()


@dataclass
class IFCBZippedBin:
    """A zipped bin from ifcb-dashboard"""
    ifcb_id: str
    time: datetime.datetime
    images: Dict
    filenames: Dict

    def __init__(self, zip_url: Union[str, Path]) -> None:
        # option to handle filepaths
        if isinstance(zip_url, Path):
            with open(zip_url, 'rb') as f:
                file_content = f.read()
        else:
            response = requests.get(zip_url)
            file_content = response.content

        # iterate over files contained in the zip to extract images
        self.images = {}
        self.filenames = {}
        with zipfile.ZipFile(io.BytesIO(file_content)) as zip_file:
            for file_in_zip in zip_file.infolist():
                if '.png' not in file_in_zip.filename:
                    continue

                with zip_file.open(file_in_zip) as f:
                    roi = int(f.name.split('.')[0].split('_')[-1])
                    self.filenames[roi] = f.name
                    self.images[roi] = bytearray(f.read())

        # extract time + ifcb from first file in bin
        # - it is the same for every image
        # DYYYMMDDTHHMMSSZ_IFCBNNN_NNNNN.png
        time, ifcb_id, _ = f.name.split('.')[0].split('_')
        self.time = datetime.datetime.strptime(time, 'D%Y%m%dT%H%M%S')
        self.ifcb_id = ifcb_id.upper()

    def to_record(self, roi) -> dict:
        """Return record representation of ROI image"""
        return {
            'ifcb_id': self.ifcb_id,
            'datetime': int(self.time.timestamp()),
            'roi': roi,
            'image': base64.b64encode(self.images[roi]).decode('utf-8')
        }

    def to_key(self, roi) -> str:
        """Return PID as unique key for object"""
        time = f'{self.time:%Y%m%dT%H%M%S}'
        return f'D{time}_{self.ifcb_id}_{roi:05}'


class IFCBImageIngestor:

    def __init__(self, ifcb_url: str, producer_config: dict) -> None:
        logger.info(f"Ingesting image data to {producer_config['bootstrap.servers']} from {ifcb_url}")
        self.ifcb_url = ifcb_url
        self.producer = SerializingProducer(producer_config)

    def publish_ifcb_image_feed(self, ifcb_url: str, topic: str, nbins: int = 1) -> None:
        """Ingest newest N image bins to a Kafka topic from an IFCB dashboard"""
        logger.info(f'Ingesting last {nbins} bin(s) of data from {ifcb_url}')

        feed = requests.get(ifcb_url + 'feed.json')
        latest_bins = feed.json()
        for bin in latest_bins[:nbins]:
            self._download_and_publish_image_bin(bin['pid'], topic)

        # wait for outstanding messages and delievery reports
        self.producer.flush()

    def publish_ifcb_image_station(self, ifcb_url: str, topic: str, nbins: int = 1) -> None:
        """Ingest oldest N image bins to a Kafka topic from an IFCB dashboard"""
        logger.info(f'Streaming all bins of data from {ifcb_url}')

        bin_count = 0
        date = self._get_earliest_date()
        while date <= datetime.datetime.today() and bin_count < nbins:
            daily_bins = requests.get(ifcb_url + f"/api/feed/day/{date.strftime('%Y-%m-%d')}")
            for bin in daily_bins.json():
                try:
                    self._download_and_publish_image_bin(bin['pid'], topic)
                except:  # noqa
                    continue
                bin_count += 1

        # wait for outstanding messages and delievery reports
        self.producer.flush()

    def _get_earliest_date(self) -> datetime.datetime:
        """Given IFCB URL (namespace), return the earliest date that data is available"""
        # Use impossibly early date used to determine earliest date
        earliest = requests.get(self.ifcb_url + '/api/feed/nearest/2000-01-01')
        earliest_date = earliest.json()['date']
        return datetime.datetime.strptime(earliest_date, '%Y-%m-%dT%H:%M:%SZ')

    def _download_and_publish_image_bin(self, bin_pid: str, topic: str) -> None:
        """Download, unzip, and publish image from the bin pid (url)"""
        zip_url = bin_pid + '.zip'
        logger.info(f'loading {zip_url}')
        image_bin = IFCBZippedBin(zip_url)

        for roi in image_bin.filenames.keys():
            logger.debug(f'publishing {image_bin.filenames[roi]}')
            # DYYYYMMDDTHHMMSSZ_IFCBNNN_NNNNN.png
            self.producer.poll(0)
            self.producer.produce(
                topic=topic,
                key=image_bin.to_key(roi),
                value=json.dumps(image_bin.to_record(roi)),
                on_delivery=delivery_report
            )


def delivery_report(err: str, msg: Message) -> None:
    """Callback for Kafka message delivery"""
    if err is not None:
        logger.info(f'Message delivery failed: {err}')
    else:
        logger.info(f'Message delivered to topic: {msg.topic()}, partition: {msg.partition()}, offset: {msg.offset()}')


@app.command()
def publish_feed_images(
    ifcb_url: str,
    topic: str,
    bootstrap_servers: str,
    nbins: int = typer.Option(1, help="Number of bins to stream. '-1' will stream an entire station")
 ):
    """Stream last N features from an ifcb-dashboard feed to Kafka."""
    producer_config = {
        'bootstrap.servers': bootstrap_servers,
    }
    ifcb_ingestor = IFCBImageIngestor(
        ifcb_url,
        producer_config
    )
    ifcb_ingestor.publish_ifcb_image_feed(ifcb_url, topic, nbins)


@app.command()
def publish_station_images(
    ifcb_url: str,
    topic: str,
    bootstrap_servers: str,
    nbins: int = typer.Option(1, help="Number of bins to stream. '-1' will stream an entire station")
 ):
    """Stream first N images from an ifcb-dashboard to Kafka."""
    producer_config = {
        'bootstrap.servers': bootstrap_servers,
    }
    ifcb_ingestor = IFCBImageIngestor(
        ifcb_url,
        producer_config
    )
    ifcb_ingestor.publish_ifcb_image_station(ifcb_url, topic, nbins)


if __name__ == '__main__':
    app()
