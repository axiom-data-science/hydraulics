import datetime
import json
from pathlib import Path
from unittest import mock

import pytest
import responses
from confluent_kafka import Consumer

from hydraulics.ifcb import image_ingestor


class TestZippedBin:
    fname = 'D20190728T212639_IFCB104.zip'
    zip_path = Path(__file__).parent / 'data' / fname
    test_url = f'http://128.114.25.154:8888/IFCB104/{fname}'

    def test_zipped_image_file(self):
        ifcb_zipped_image = image_ingestor.IFCBZippedBin(self.zip_path)

        record = ifcb_zipped_image.to_record(2)
        assert record['ifcb_id'] == 'IFCB104'
        assert record['datetime'] == 1564374399
        assert record['roi'] == 2
        assert len(record['image']) == 15728

        key = ifcb_zipped_image.to_key(2)
        assert key == 'D20190728T212639_IFCB104_00002'

#    def test_zipped_image_url(self):
    def zipped_image_url(self):
        ifcb_zipped_image = image_ingestor.IFCBZippedBin(self.test_url)

        record = ifcb_zipped_image.to_record(2)
        assert record['ifcb_id'] == 'IFCB104'
        assert record['datetime'] == 1564374399
        assert record['roi'] == 2
        assert len(record['image']) == 15728

        key = ifcb_zipped_image.to_key(2)
        assert key == 'D20190728T212639_IFCB104_00002'


class TestIFCBImage:
    producer_config = {
        'bootstrap.servers': 'localhost:9092'
    }
    consumer_config = {
        'bootstrap.servers': 'localhost:9092',
        'group.id': 'ifcb-test',
        'auto.offset.reset': 'earliest'
    }
    ifcb_url = 'http://fake.ifcb.edu/IFCB187'
    bin_pid = 'D20190728T212639_IFCB104'
    fname = f'{bin_pid}.zip'
    zip_path = Path(__file__).parent / 'data' / fname
    ifcb_zipped_bin = image_ingestor.IFCBZippedBin(zip_path)

    @responses.activate
    def test_get_earliest_date(self):

        # mock response from ifcb-dashboard
        responses.add(
            responses.GET,
            self.ifcb_url + '/api/feed/nearest/2000-01-01',
            json={
                'date': '2001-02-03T01:02:03Z',
                'pid': 'http://fake.ifcb.edu/IFCB187/D20010203T010203_IFCB187'
            },
            status=400
        )

        ifcb_ingestor = image_ingestor.IFCBImageIngestor(self.ifcb_url, self.producer_config)
        earliest_date = ifcb_ingestor._get_earliest_date()

        assert earliest_date == datetime.datetime(2001, 2, 3, 1, 2, 3)

    @pytest.mark.kafka
    @mock.patch('hydraulics.ifcb.image_ingestor.IFCBZippedBin', autospec=True)
    def test_download_and_publish_image_bin(self, MockedIFCBZippedBin):
        # Mock IFCBZippedBin to return the bin saved in repo
        MockedIFCBZippedBin.return_value = self.ifcb_zipped_bin

        ifcb_ingestor = image_ingestor.IFCBImageIngestor(self.ifcb_url, self.producer_config)
        topic = 'test-ifcb-publish'
        ifcb_ingestor._download_and_publish_image_bin(self.bin_pid, topic)
        assert MockedIFCBZippedBin.called

        consumer = Consumer(self.consumer_config)
        consumer.subscribe([topic])
        data = json.loads(consumer.poll(5).value())

        assert data['ifcb_id'] == 'IFCB104'
        assert data['datetime'] == 1564374399
        assert data['roi'] == 2
        assert len(data['image']) == 15728
