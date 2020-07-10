import base64
import io
import unittest
from pathlib import Path

import numpy as np

from hydraulics.ifcb import image_ingestor
from hydraulics.ifcb.blob import (
    Blob,
    BlobConfig
)


class TestBlob(unittest.TestCase):

    def setUp(self) -> None:
        zfname = 'D20190728T212639_IFCB104.zip'
        fname = 'test.png'
        blob_img = 'blob_test_image.png'
        self.zip_path = Path(__file__).parent / 'data' / zfname
        self.img_path = Path(__file__).parent / 'data' / fname
        self.blob_img_path = Path(__file__).parent / 'data' / blob_img
        self.config = BlobConfig()
        self.zipped_image = image_ingestor.IFCBZippedBin(self.zip_path)

    def test_str_load(self):
        blob = Blob(str(self.img_path), self.config)

        assert isinstance(blob.img, np.ndarray)
        assert blob.img.sum() == 3359800
        assert blob.img.shape == (138, 176)

    def test_path_load(self):
        blob = Blob(self.img_path, self.config)

        assert isinstance(blob.img, np.ndarray)
        assert blob.img.sum() == 3359800
        assert blob.img.shape == (138, 176)

    def test_bytes_load(self):
        record = self.zipped_image.to_record(2)
        img_str = base64.b64decode(record['image'])
        blob = Blob(img_str, self.config)

        assert isinstance(blob.img, np.ndarray)
        assert blob.img.sum() == 3359800
        assert blob.img.shape == (138, 176)

    def test_bytesio_load(self):
        record = self.zipped_image.to_record(2)
        img_str = base64.b64decode(record['image'])
        img_file = io.BytesIO(img_str)
        blob = Blob(img_file, self.config)

        assert isinstance(blob.img, np.ndarray)
        assert blob.img.sum() == 3359800
        assert blob.img.shape == (138, 176)

    def test_apply_phasecong(self):
        blob = Blob(self.blob_img_path, self.config)
        M, m = blob._apply_phasecong()
        Mm = M + m

        assert isinstance(Mm, np.ndarray)
        assert Mm.shape == (220, 446)
        assert np.isclose(Mm.sum(), 4603.975603416737)

    def test_edge_and_corners(self):
        blob = Blob(self.blob_img_path, self.config)
        edge_and_corners = blob._extract_edges_and_corners()

        assert isinstance(edge_and_corners, np.ndarray)
        assert edge_and_corners.shape == (220, 446)
        assert edge_and_corners.sum() == 16360

    def test_apply_closing(self):
        blob = Blob(self.blob_img_path, self.config)
        blob_img = blob._extract_edges_and_corners()
        dark_img = blob._apply_dark_thresholding()
        blob_img = blob_img | dark_img
        closed = blob._apply_closing(blob_img)

        assert isinstance(closed, np.ndarray)
        assert closed.shape == (220, 446)
        assert closed.sum() == 22199

    def test_apply_dilation(self):
        blob = Blob(self.blob_img_path, self.config)
        blob_img = blob._extract_edges_and_corners()
        dark_img = blob._apply_dark_thresholding()
        blob_img = blob_img | dark_img
        closed = blob._apply_closing(blob_img)
        dilated = blob._apply_dilation(closed)

        assert isinstance(dilated, np.ndarray)
        assert dilated.shape == (220, 446)
        assert dilated.sum() == 25902

    def test_apply_morph_thinning(self):
        blob = Blob(self.blob_img_path, self.config)
        img_dark = blob._apply_dark_thresholding()
        img_blob = blob._extract_edges_and_corners()
        img_blob = img_blob | img_dark
        img_blob = blob._apply_closing(img_blob)
        img_blob = blob._apply_dilation(img_blob)
        thinned = blob._apply_morph_thinning(img_blob)

        assert isinstance(thinned, np.ndarray)
        assert thinned.shape == (220, 446)
        assert thinned.sum() == 21013

    def test_fill_and_remove_small_holes(self):
        blob = Blob(self.blob_img_path, self.config)
        img_dark = blob._apply_dark_thresholding()
        img_blob = blob._extract_edges_and_corners()
        img_blob = img_blob | img_dark
        img_blob = blob._apply_closing(img_blob)
        img_blob = blob._apply_dilation(img_blob)
        thinned = blob._apply_morph_thinning(img_blob)

        img = blob._fill_and_remove_holes(thinned)

        assert isinstance(img, np.ndarray)
        assert img.shape == (220, 446)
        assert img.sum() == 21987

    def test_blob(self):
        blob = Blob(self.blob_img_path, self.config)

        assert isinstance(blob.blob_img, np.ndarray)
        assert blob.blob_img.shape == (220, 446)
        assert blob.blob_img.sum() == 21987

    def test_add_properties(self):
        blob = Blob(self.blob_img_path, self.config)

        assert blob.area == 21987
        assert np.isclose(blob.equivalent_diameter, 167.31622118041042)
        assert np.isclose(blob.major_axis_length, 274.93638304044634)
        assert np.isclose(blob.eccentricity, 0.8355355954192663)
