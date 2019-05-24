"""
Display one markers layer ontop of one image layer using the add_markers and
add_image APIs
"""

import numpy as np
from skimage import data
import napari
from napari.util import app_context

print("click to add markers; close the window when finished.")

with app_context():
    viewer = napari.view(data.astronaut(), multichannel=True)
    markers = viewer.add_markers(np.zeros((0, 2)))
    markers.mode = 'add'

print("you clicked on:")
print(markers.coords)
