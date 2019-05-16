"""
Display one shapes layer ontop of one image layer using the add_shapes and
add_image APIs. When the window is closed it will print the coordinates of
your shapes.
"""

import numpy as np
from imageio import imread
from napari import ViewerApp
from napari.util import app_context
from vispy.color import Colormap


photographer = imread('imageio:camera.png')

with app_context():
    # create the viewer and window
    viewer = ViewerApp()

    # add the image
    img_layer = viewer.add_image(photographer, name='photographer')
    img_layer.colormap = 'gray'

    # create a list of polygons
    polygons = [np.array([[11,   13], [111, 113], [22, 246]]),
                np.array([[505,  60], [402,  71], [383,  42], [251,  95],
                          [212,  59], [131, 137], [126, 187], [191, 204],
                          [171, 248], [211, 260], [273, 243], [264, 225],
                          [430, 173], [512, 160]]),
                np.array([[310, 382], [229, 381], [209, 401], [221, 411],
                          [258, 411], [300, 412], [306, 435], [268, 434],
                          [265, 454], [298, 461], [307, 461], [307, 507],
                          [349, 510], [352, 369], [330, 366], [330, 366]])]

    # add polygons
    layer = viewer.add_shapes(polygons, shape_type='polygon', edge_width=1,
                              edge_color='coral', face_color='royalblue',
                              name='shapes')

    # change some properties of the layer
    layer.selected_shapes = list(range(len(layer.data.shapes)))
    layer.edge_width = 5
    layer.opacity = 0.75
    layer.selected_shapes = []

    # add an ellipse to the layer
    ellipse = np.array([[59, 222], [110, 289], [170, 243], [119, 176]])
    layer.add_shapes(ellipse, shape_type='ellipse', edge_width=5,
                     edge_color='coral', face_color='purple',
                     opacity=0.75)
    layer.refresh()

    layer._qt_properties.setExpanded(True)

    masks = layer.data.to_masks([512, 512])
    masks_layer = viewer.add_image(masks.astype(float), name='masks')
    masks_layer.opacity = 0.7
    masks_layer.colormap = Colormap([[0.0, 0.0, 0.0, 0.0],
                                     [1.0, 0.0, 0.0, 1.0]])

    labels = layer.data.to_labels([512, 512])
    labels_layer = viewer.add_labels(labels, name='labels')
    labels_layer.visible = False
