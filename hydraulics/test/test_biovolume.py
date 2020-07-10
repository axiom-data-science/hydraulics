import unittest
from pathlib import Path

import numpy as np

from hydraulics.ifcb.blob import (
    Blob,
    BlobConfig
)
from hydraulics.ifcb import biovolume


class TestBiovolume(unittest.TestCase):
    blob_img = 'blob_test_image.png'
    blob_img_path = Path(__file__).parent / 'data' / blob_img
    config = BlobConfig()

    def test_distmap_volume(self):
        blob = Blob(self.blob_img_path, self.config)
        volume, x = biovolume.calc_distmap_volume(blob.blob_img)

        assert isinstance(volume, float)
        assert np.isclose(volume, 1087116.7156675349)
        assert isinstance(x, float)
        assert np.isclose(x, 62.96125906574407)

    def test_sor_volume(self):
        blob = Blob(self.blob_img_path, self.config)

        sor_volume = biovolume.calc_sor_volume(blob.blob_img)
        assert isinstance(sor_volume, float)
        assert np.isclose(sor_volume, 2131048.325682015)

    def test_volume(self):
        blob = Blob(self.blob_img_path, self.config)

        volume = biovolume.calc_biovolume(blob)
        assert isinstance(volume, float)
        assert np.isclose(volume, 1087116.7156675349)
