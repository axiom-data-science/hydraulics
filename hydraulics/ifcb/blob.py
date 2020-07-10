import io
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple, Union

import numpy as np
from phasepack import phasecong
from scipy.cluster.vq import kmeans2
from skimage.filters.thresholding import apply_hysteresis_threshold
from scipy.ndimage import (
    binary_fill_holes
)
from skimage.io import imread
from skimage.measure import regionprops
from skimage.morphology import (
    binary_closing,
    binary_dilation,
    remove_small_objects,
    thin
)


@dataclass
class BlobConfig:
    """Config for blob extraction.

    Values taken from:
    - ifcb-analysis/feature_extraction/configure.m
    - ifcb-analysis/feature_extraction/kmean_segment.m
    """
    # phasecong
    pc_nscale = 4
    pc_norient = 6
    pc_minWaveLength = 2
    pc_mult = 2.5
    pc_sigmaOnf = 0.55
    pc_k = 2.0
    pc_cutOff = 0.3
    pc_g = 5
    pc_noiseMethod = -1

    # hysteresis thresholds
    hysthresh_T1 = 0.2
    hysthresh_T2 = 0.1

    # dark threshold
    dark_threshold = 0.65

    # minimum blob size
    blob_min = 150


class Blob:
    """Given an IFCB image file, create blob img, and calculate blob properites.

    Notes:
    - port of ifcb-analysis/feature_extraction/blob.m
    - blob derived from https://github.com/WHOIGit/ifcb-segmentation-whitebox/blob/master/index.ipynb
    """
    def __init__(
        self,
        img_file: Union[bytes, io.BytesIO, str, Path],
        config: BlobConfig,
    ) -> None:
        if isinstance(img_file, bytes):
            self.img = imread(io.BytesIO(img_file))
        elif isinstance(img_file, io.BytesIO):
            self.img = imread(img_file)
        elif isinstance(img_file, (str, Path)):
            self.img = imread(img_file)
        else:
            raise TypeError(f'img_file {img_file} type {type(img_file)} not supported')

        self.config = config
        self._make_blob()

    def _apply_phasecong(self) -> Tuple[np.ndarray, np.ndarray]:
        """Apply phasecong to image and return (M, m)

        Notes:
        - M (Maximum moment of phase congruency covariance - edge strength)
        - m (minimum moment of phase congruency covariance - corner strength)
        """
        results = phasecong(
            self.img,
            self.config.pc_nscale,
            self.config.pc_norient,
            self.config.pc_minWaveLength,
            self.config.pc_mult,
            self.config.pc_sigmaOnf,
            self.config.pc_k,
            self.config.pc_cutOff,
            self.config.pc_g,
            self.config.pc_noiseMethod
        )
        # results[0] = M, results[1] = m
        return results[0], results[1]

    def _extract_edges_and_corners(self):
        """Extract edges and corners"""
        M, m = self._apply_phasecong()
        edge_and_corners = apply_hysteresis_threshold(
            M+m,
            self.config.hysthresh_T1,
            self.config.hysthresh_T2,
        )
        return self._clean_image_edges(edge_and_corners)

    def _clean_image_edges(self, edge_and_corners: np.ndarray) -> np.ndarray:
        """Clean spurious edges along margins of given image.

        Notes:
        - Ensure that 1 (true) values along outside edge are adjacent to an interior value of 1
        - If not, make that margin value 0
        """
        # top row
        edge_and_corners[0, edge_and_corners[1, :] == 0] = 0
        # bottom row
        edge_and_corners[-1, edge_and_corners[-2, :] == 0] = 0
        # 1st column
        edge_and_corners[edge_and_corners[:, 1] == 0, 0] = 0
        # last column
        edge_and_corners[edge_and_corners[:, -2] == 0, -1] = 0

        return edge_and_corners

    def _apply_dark_thresholding(self) -> np.ndarray:
        """Given original image identify dark areas that should be included in blob

        Notes:
        - From https://github.com/WHOIGit/ifcb-segmentation-whitebox/blob/master/index.ipynb
        """
        means, _ = kmeans2(
            self.img.reshape((self.img.size, 1)).astype(np.float),
            2
        )
        thresh = np.mean(means)
        return self.img < (thresh * self.config.dark_threshold)

    def _apply_closing(self, img: np.ndarray) -> np.ndarray:
        """Apply morphological closing to an image"""
        kernel = np.ones((5, 5), dtype=np.bool)
        return binary_closing(img, kernel)

    def _apply_dilation(self, img: np.ndarray) -> np.ndarray:
        """Apply morphological dilation to an image"""
        kernel = np.array(
            [[0, 0, 1, 0, 0],
             [0, 1, 1, 1, 0],
             [1, 1, 1, 1, 1],
             [0, 1, 1, 1, 0],
             [0, 0, 1, 0, 0]],
            dtype=np.bool
        )
        return binary_dilation(img, kernel)

    def _apply_morph_thinning(self, img: np.ndarray, niter: int = 3) -> np.ndarray:
        """Apply morphological thinning."""
        thin_img = thin(img, niter)

        return thin_img

    def _fill_and_remove_holes(self, img: np.ndarray, min_size=150, connectivity=3) -> np.ndarray:
        filled = binary_fill_holes(img)
        blob = remove_small_objects(filled, min_size, connectivity)

        return blob

    def _make_blob(self) -> None:
        img_blob = self._extract_edges_and_corners()
        img_dark = self._apply_dark_thresholding()
        img_blob = img_blob | img_dark
        img_blob = self._apply_closing(img_blob)
        img_blob = self._apply_dilation(img_blob)
        img_blob = self._apply_morph_thinning(img_blob)
        self.blob_img = self._fill_and_remove_holes(img_blob)

        self._add_properties()

    def _add_properties(self) -> None:
        region_props = regionprops(self.blob_img.astype(np.uint8))[0]
        self.area = region_props.area
        self.equivalent_diameter = region_props.equivalent_diameter
        self.major_axis_length = region_props.major_axis_length
        self.eccentricity = region_props.eccentricity
