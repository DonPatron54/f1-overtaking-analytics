"""Unit tests for the geometric circuit features."""

import numpy as np
import pytest

from src.circuit_features import straight_lengths


def test_rectangle_has_four_straights():
    # 1000 m x 500 m rectangle with intermediate points on the long sides
    coords = np.array([[0, 0], [500, 0], [1000, 0], [1000, 500], [0, 500], [0, 0]])
    runs = sorted(straight_lengths(coords))
    assert runs == pytest.approx([500, 500, 1000, 1000])


def test_gentle_kink_stays_one_straight():
    # 5 degree kink in the middle of an 800 m straight, then a hairpin back
    kink = np.radians(5)
    coords = np.array([[0, 0], [400, 0],
                       [400 + 400 * np.cos(kink), 400 * np.sin(kink)],
                       [0, 60], [0, 0]])
    assert max(straight_lengths(coords)) == pytest.approx(800, rel=1e-3)
