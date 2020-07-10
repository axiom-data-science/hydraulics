"""Compute biovolume

Notes:
- https://github.com/joefutrelle/oii/blob/master/ifcb2/features/biovolume.py
- Derived from ifcb-analysis/feature_exctraction/biovolume.m
"""
from typing import Tuple

import numpy as np
from scipy.ndimage.morphology import distance_transform_edt
from scipy.ndimage import correlate
from scipy.spatial import ConvexHull
from skimage.draw import polygon, line

from blob import Blob


def find_perimeter(blob_img: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    blob_img = np.array(blob_img).astype(np.bool) * 1
    """Given image return boundaries.

    Notes:
    - Boundaries found via erosion and logical using four-connectivity
    """
    kernel = np.array(
        [[0,  -1,  0],
         [-1,  4, -1],
         [0,  -1,  0]]
    )
    return correlate(blob_img, kernel) > 0


def calc_distmap_volume(blob_img: np.ndarray, perimeter_image: np.ndarray = None) -> Tuple[float, float]:
    """Given blob image, calculate and return biovolume

    Notes:
    - Moberg and Sosik (2012), Limnology and Oceanography: Methods
    """
    if perimeter_image is None:
        perimeter_image = find_perimeter(blob_img)

    # calculate distance map
    D = distance_transform_edt(1 - perimeter_image) + 1
    D = D * (blob_img > 0)
    Dm = np.ma.array(D, mask=1 - blob_img)

    # representative transect
    x = 4 * np.ma.mean(Dm) - 2

    # define cross-section correction factors
    # pyramidal cross-section to interpolated diamond
    c1 = x**2 / (x**2 + 2*x + 0.5)

    # diamond to circumscribing circle
    c2 = np.pi / 2
    volume = c1 * c2 * 2 * np.sum(D)

    # return volume and representative transect
    return volume, x


def calc_sor_volume(blob_img: np.ndarray) -> float:
    """Given blob image, calculate and return biovolume

    Notes:
    - volumewalk.m in ifcb-analysis
    """
    C = np.sum(blob_img.astype(np.bool), axis=0) * 0.5
    return np.sum(C**2 * np.pi)


def convex_hull(perimeter_points: np.ndarray) -> np.ndarray:
    """Given perimeter points, return the convex hull"""
    P = np.vstack(perimeter_points).T
    hull = ConvexHull(P)
    return P[hull.vertices]


def convex_hull_image(hull: np.ndarray, shape: Tuple[int, int]) -> np.ndarray:
    """Create image of convex hull"""
    chi = np.zeros(shape, dtype=np.bool)
    # points in the convex hull
    y, x = polygon(hull[:, 0], hull[:, 1])
    chi[y, x] = 1
    # points on the convex hull
    for row in np.hstack((hull, np.roll(hull, 1, axis=0))):
        chi[line(*row)] = 1
    return chi


def calc_biovolume(blob: Blob) -> float:
    """Given blob img, return biovolume

    Notes:
    - https://github.com/joefutrelle/oii/blob/master/ifcb2/features/biovolume.py
    - Derived from ifcb-analysis/feature_exctraction/biovolume.m
    """
    perimeter_points = np.where(find_perimeter(blob.blob_img))
    chull = convex_hull(perimeter_points)
    chull_img = convex_hull_image(chull, blob.blob_img.shape)
    convex_area = np.sum(chull_img)

    area_ratio = float(convex_area) / blob.area
    p = blob.equivalent_diameter / blob.major_axis_length
    if (area_ratio < 1.2) or (blob.eccentricity < 0.8 and p > 0.8):
        return calc_sor_volume(blob.blob_img)
    else:
        return calc_distmap_volume(blob.blob_img)[0]
