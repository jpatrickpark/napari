import numpy as np
from scipy import ndimage as ndi
from copy import copy

from .._base_layer import Layer
from ..._vispy.scene.visuals import Image as ImageNode

from ...util.colormaps import colormaps
from ...util.event import Event

from .._register import add_to_viewer

from .view import QtLabelsLayer
from .view import QtLabelsControls
from ._constants import Mode, BACKSPACE


@add_to_viewer
class Labels(Layer):
    """Labels (or segmentation) layer.

    An image layer where every pixel contains an integer ID corresponding
    to the region it belongs to.

    Parameters
    ----------
    image : np.ndarray
        Image data.
    meta : dict, optional
        Image metadata.
    multichannel : bool, optional
        Whether the image is multichannel. Guesses if None.
    opacity : float, optional
        Opacity of the labels, must be between 0 and 1.
    name : str, keyword-only
        Name of the layer.
    **kwargs : dict
        Parameters that will be translated to metadata.
    """

    _brush_shapes = ['circle', 'square']

    def __init__(self, label_image, meta=None, *, opacity=0.7, name=None,
                 **kwargs):
        if name is None and meta is not None:
            if 'name' in meta:
                name = meta['name']

        visual = ImageNode(None, method='auto')
        super().__init__(visual, name)
        self.events.add(colormap=Event, mode=Event, n_dimensional=Event,
                        contiguous=Event, brush_size=Event, brush_shape=Event,
                        selected_label=Event)

        self._raw_image = label_image
        self._max_label = np.max(label_image)
        if self._max_label == 0:
            self._image = label_image.astype('float')
        else:
            self._image = label_image / self._max_label

        self._meta = meta
        self.interpolation = 'nearest'
        self.colormap_name = 'random'
        self.colormap = colormaps.label_colormap(label_image,
                                                 max_label=self._max_label)


        self._node.opacity = opacity
        self._n_dimensional = True
        self._contiguous = True
        self._brush_size = 10
        self._brush_color = 'white'
        self._brush_shape = 'circle'

        self._selected_label = 0
        self._selected_color = None

        self._mode = Mode.PAN_ZOOM
        self._mode_history = self._mode
        self._status = str(self._mode)
        self._help = 'enter paint or fill mode to edit labels'



        # update flags
        self._need_display_update = False
        self._need_visual_update = False

        self._qt_properties = QtLabelsLayer(self)
        self._qt_controls = QtLabelsControls(self)

        self._node.clim = [0., 1.]
        self.events.colormap()

    def new_colormap(self):
        seed = np.random.random((3,))
        self.colormap = colormaps.label_colormap(self._image, seed=seed)
        self.events.colormap()
        self._refresh_selected_color()
        self.events.selected_label()

    def label_color(self, label):
        """Return the color corresponding to a specific label."""
        return self.colormap.map(label / self._max_label)[0]

    @property
    def image(self):
        """np.ndarray: Image data.
        """
        return self._image

    @image.setter
    def image(self, image):
        self._image = image
        self.refresh()

    @property
    def meta(self):
        """dict: Image metadata.
        """
        return self._meta

    @meta.setter
    def meta(self, meta):
        self._meta = meta
        self.refresh()

    @property
    def data(self):
        """tuple of np.ndarray, dict: Image data and metadata.
        """
        return self.image, self.meta

    @data.setter
    def data(self, data):
        self._image, self._meta = data
        self.refresh()

    @property
    def contiguous(self):
        """ bool: if True, fill changes only pixels of the same label that are
        contiguous with the one clicked on.
        """
        return self._contiguous

    @contiguous.setter
    def contiguous(self, contiguous):
        self._contiguous = contiguous
        self.events.contiguous()

        self.refresh()

    @property
    def n_dimensional(self):
        """ bool: if True, edits labels not just in central plane but also
        in all n dimensions according to specified brush size or fill.
        """
        return self._n_dimensional

    @n_dimensional.setter
    def n_dimensional(self, n_dimensional):
        self._n_dimensional = n_dimensional
        self.events.n_dimensional()

        self.refresh()

    @property
    def brush_size(self):
        """ float | list: Size of the paint brush. If a float, then if
        `n_dimensional` is False applies just to the visible dimensions, if
        `n_dimensional` is True applies to all dimensions. If a list, must be
        the same length as the number of dimensions of the layer, and size
        applies to each dimension scaled by the appropriate amount.
        """
        return self._brush_size

    @brush_size.setter
    def brush_size(self, brush_size):
        self._brush_size = int(brush_size)
        self.cursor_size = self._brush_size/self._get_rescale()
        self.events.brush_size()

        self.refresh()

    @property
    def brush_shape(self):
        """ str: Shape of the paint brush, one of "{'square', 'circle'}"
        """
        return self._brush_shape

    @brush_shape.setter
    def brush_shape(self, brush_shape):
        if brush_shape not in self._brush_shapes:
            raise ValueError('Brush shape not recognized')
        self._brush_shape = brush_shape
        self.events.brush_shape()

        self.refresh()

    @property
    def selected_label(self):
        """ int: Index of selected label. If `0` corresponds to the transparent
        background. If greater than the current maximum label then if used to
        fill or paint a region this label will be added to the new labels
        """
        return self._selected_label

    @selected_label.setter
    def selected_label(self, selected_label):
        self._selected_label = selected_label
        self._refresh_selected_color()
        self.events.selected_label()

        self.refresh()

    def _refresh_selected_color(self):
        """Sets `selected_color` to be the color of the currently selected
        label.
        """
        if self.selected_label == 0:
            # If background
            self._selected_color = None
        elif self.selected_label <= self._max_label:
            # If one of the existing labels
            self._selected_color = self.label_color(self.selected_label)
        else:
            # If a new label make None
            # NEED TO IMPLEMENT BETTER COLOR SELECTION
            self._selected_color = None

    @property
    def mode(self):
        """MODE: Interactive mode. The normal, default mode is PAN_ZOOM, which
        allows for normal interactivity with the canvas.

        In PICKER mode the cursor functions like a color picker, setting the
        clicked on label to be the curent label. If the background is picked it
        will select the background label `0`.

        In PAINT mode the cursor functions like a paint brush changing any
        pixels it brushes over to the current label. If the background label
        `0` is selected than any pixels will be changed to background and this
        tool functions like an eraser. The size and shape of the cursor can be
        adjusted in the properties widget.

        In FILL mode the cursor functions like a fill bucket replacing pixels
        of the label clicked on with the current label. It can either replace
        all pixels of that label or just those that are contiguous with the
        clicked on pixel. If the background label `0` is selected than any
        pixels will be changed to background and this tool functions like an
        eraser.
        """
        return self._mode

    @mode.setter
    def mode(self, mode):
        if mode == self._mode:
            return
        old_mode = self._mode
        if mode == Mode.PAN_ZOOM:
            self.cursor = 'standard'
            self.interactive = True
            self.help = 'enter paint or fill mode to edit labels'
        elif mode == Mode.PICKER:
            self.cursor = 'cross'
            self.interactive = False
            self.help = ('hold <space> to pan/zoom, '
                         'click to pick a label')
        elif mode == Mode.PAINT:
            self.cursor_size = self.brush_size/self._get_rescale()
            self.cursor = 'square'
            self.interactive = False
            self.help = ('hold <space> to pan/zoom, '
                         'drag to paint a label')
        elif mode == Mode.FILL:
            self.cursor = 'cross'
            self.interactive = False
            self.help = ('hold <space> to pan/zoom, '
                         'click to fill a label')
        else:
            raise ValueError("Mode not recongnized")

        self.status = str(mode)
        self._mode = mode

        self.events.mode(mode=mode)
        self.refresh()

    def _get_shape(self):
        return self.image.shape

    def _update(self):
        """Update the underlying visual.
        """
        if self._need_display_update:
            self._need_display_update = False

            self.viewer.dims._child_layer_changed = True
            self.viewer.dims._update()

            self._node._need_colortransform_update = True
            self._set_view_slice(self.viewer.dims.indices)

        if self._need_visual_update:
            self._need_visual_update = False
            self._node.update()

    def _refresh(self):
        """Fully refresh the underlying visual.
        """
        self._need_display_update = True
        self._update()

    def _get_rescale(self):
        """Get conversion factor from canvas coordinates to image coordinates.
        Depends on the current zoom level.

        Returns
        ----------
        rescale : float
            Conversion factor from canvas coordinates to image coordinates.
        """
        transform = self.viewer._canvas.scene.node_transform(self._node)
        rescale = transform.map([1, 1])[:2] - transform.map([0, 0])[:2]

        return rescale.mean()

    def _slice_image(self, indices, image=None):
        """Determines the slice of image given the indices.

        Parameters
        ----------
        indices : sequence of int or slice
            Indices to slice with.
        image : array, optional
            The image to slice. Defaults to self._image if None.

        Returns
        -------
        sliced : array or value
            The requested slice.
        slice_indices : tuple
            Tuple of indices corresponding to the slice
        """
        if image is None:
            image = self._image
        ndim = self.ndim
        indices = list(indices)[:ndim]

        for dim in range(len(indices)):
            max_dim_index = self.image.shape[dim] - 1

            try:
                if indices[dim] > max_dim_index:
                    indices[dim] = max_dim_index
            except TypeError:
                pass

        slice_indices = tuple(indices)
        return image[slice_indices], slice_indices

    def _set_view_slice(self, indices):
        """Sets the view given the indices to slice with.

        Parameters
        ----------
        indices : sequence of int or slice
            Indices to slice with.
        """
        sliced_image, slice_indices = self._slice_image(indices)
        self._node.set_data(sliced_image)

        self._need_visual_update = True
        self._update()

    @property
    def method(self):
        """string: Selects method of rendering image in case of non-linear
        transforms. Each method produces similar results, but may trade
        efficiency and accuracy. If the transform is linear, this parameter
        is ignored and a single quad is drawn around the area of the image.

            * 'auto': Automatically select 'impostor' if the image is drawn
              with a nonlinear transform; otherwise select 'subdivide'.
            * 'subdivide': ImageVisual is represented as a grid of triangles
              with texture coordinates linearly mapped.
            * 'impostor': ImageVisual is represented as a quad covering the
              entire view, with texture coordinates determined by the
              transform. This produces the best transformation results, but may
              be slow.
        """
        return self._node.method

    @method.setter
    def method(self, method):
        self._node.method = method

    def fill(self, indices, coord, old_label, new_label):
        """Replace an existing label with a new label, either just at the
        connected component if the `contiguous` flag is `True` or everywhere
        if it is `False`, working either just in the current slice if
        the `n_dimensional` flag is `False` or on the entire data if it is
        `True`.

        Parameters
        ----------
        indices : sequence of int or slice
            Indices that make up the slice.
        coord : sequence of int
            Position of mouse cursor in image coordinates.
        old_label : int
            Value of the label image at the coord to be replaced.
        new_label : int
            Value of the new label to be filled in.
        """
        int_coord = copy(coord)
        int_coord[0] = int(round(coord[0]))
        int_coord[1] = int(round(coord[1]))

        if self.n_dimensional or self._raw_image.ndim==2:
            # work with entire image
            labels = self._raw_image
            slice_coord = tuple(int_coord)
        else:
            # work with just the sliced image
            labels, slice_indices = self._slice_image(indices,
                                                      image=self._raw_image)
            slice_coord = tuple(int_coord[:2])

        matches = labels==old_label
        if self.contiguous:
            # if not contiguous replace only selected connected component
            labeled_matches, num_features = ndi.label(matches)
            if num_features != 1:
                match_label = labeled_matches[slice_coord]
                matches = np.logical_and(matches, labeled_matches==match_label)

        # Replace target pixels with new_label
        labels[matches] = new_label

        if not (self.n_dimensional or self._raw_image.ndim==2):
            # if working with just the slice, update the rest of the raw image
            self._raw_image[slice_indices] = labels

        # update the displayed image
        if self._max_label == 0:
            self._image =  self._raw_image.astype('float')
        else:
            self._image =  self._raw_image / self._max_label

        self.refresh()

    def _to_pix(self, pos, axis):
        """Round float from cursor position to a valid pixel

        Parameters
        ----------
        pos : float
            Float that is to be mapped.
        axis : 0 | 1
            Axis that pos corresponds to.
        Parameters
        ----------
        pix : int
            Rounded pixel value
        """

        pix = int(np.clip(round(pos), 0, self.shape[axis]))
        return pix

    def paint(self, indices, coord, new_label):
        """Paint over existing labels with a new label, using the selected
        brush shape and size, either only on the visible slice or in all
        n dimensions.

        Parameters
        ----------
        indices : sequence of int or slice
            Indices that make up the slice.
        coord : sequence of int
            Position of mouse cursor in image coordinates.
        new_label : int
            Value of the new label to be filled in.
        """
        if self.n_dimensional or self._raw_image.ndim==2:
            slice_coord = tuple([slice(self._to_pix(ind-self.brush_size/2, i),
                                       self._to_pix(ind+self.brush_size/2, i),
                                       1) for i, ind
                                in enumerate(coord)])
        else:
            slice_coord = tuple([slice(self._to_pix(ind-self.brush_size/2, i),
                                       self._to_pix(ind+self.brush_size/2, i),
                                       1) for i, ind
                                in enumerate(coord[:2])] + coord[2:])

        # print(self.brush_size/2, coord, slice_coord[:2])

        # update the raw image
        self._raw_image[slice_coord] = new_label

        # update the displayed image
        if self._max_label == 0:
            self._image =  self._raw_image.astype('float')
        else:
            self._image =  self._raw_image / self._max_label

        self.refresh()

    def get_label(self, position, indices):
        """Returns coordinates, values, and a string for a given mouse position
        and set of indices.

        Parameters
        ----------
        position : sequence of two int
            Position of mouse cursor in canvas.
        indices : sequence of int or slice
            Indices that make up the slice.

        Returns
        ----------
        coord : sequence of int
            Position of mouse cursor in image coordinates.
        label : int
            Value of the label image at the coord.
        """
        transform = self._node.canvas.scene.node_transform(self._node)
        pos = transform.map(position)
        pos = [np.clip(pos[1], 0, self.shape[0]), np.clip(pos[0], 0,
                       self.shape[1])]
        coord = copy(indices)
        coord[0] = pos[0]
        coord[1] = pos[1]
        int_coord = copy(coord)
        int_coord[0] = int(round(coord[0]))
        int_coord[1] = int(round(coord[1]))
        label, slice_indices = self._slice_image(int_coord,
                                                 image=self._raw_image)
        return coord, label

    def get_message(self, coord, label):
        """Generates a string based on the coordinates and information about
        what shapes are hovered over

        Parameters
        ----------
        coord : sequence of int
            Position of mouse cursor in image coordinates.
        label : int
            Value of the label image at the coord.

        Returns
        ----------
        msg : string
            String containing a message that can be used as a status update.
        """
        int_coord = copy(coord)
        int_coord[0] = int(round(coord[0]))
        int_coord[1] = int(round(coord[1]))
        msg = f'{int_coord}, {self.name}, label {label}'

        return msg

    def on_mouse_press(self, event):
        """Called whenever mouse pressed in canvas.

        Parameters
        ----------
        event : Event
            Vispy event
        """
        indices = self.viewer.dims.indices
        coord, label = self.get_label(event.pos, indices)

        if self.mode == Mode.PAN_ZOOM:
            # If in pan/zoom mode do nothing
            pass
        elif self.mode == Mode.PICKER:
            self.selected_label = label
        elif self.mode == Mode.PAINT:
            # Start painting with new label
            new_label = self.selected_label
            self.paint(indices, coord, new_label)
            self.status = self.get_message(coord, new_label)
        elif self.mode == Mode.FILL:
            # Fill clicked on region with new label
            old_label = label
            new_label = self.selected_label
            self.fill(indices, coord, old_label, new_label)
            self.status = self.get_message(coord, new_label)
        else:
            raise ValueError("Mode not recongnized")

    def on_mouse_move(self, event):
        """Called whenever mouse moves over canvas.

        Parameters
        ----------
        event : Event
            Vispy event
        """
        if event.pos is None:
            return
        indices = self.viewer.dims.indices
        coord, label = self.get_label(event.pos, indices)

        if self.mode == Mode.PAINT and event.is_dragging:
            new_label = self.selected_label
            self.paint(indices, coord, new_label)
            label = new_label

        self.status = self.get_message(coord, label)

    def on_key_press(self, event):
        """Called whenever key pressed in canvas.

        Parameters
        ----------
        event : Event
            Vispy event
        """
        if event.native.isAutoRepeat():
            return
        else:
            if event.key == ' ':
                if self.mode != Mode.PAN_ZOOM:
                    self._mode_history = self.mode
                    self.mode = Mode.PAN_ZOOM
                else:
                    self._mode_history = Mode.PAN_ZOOM
            elif event.key == 'p':
                self.mode = Mode.PAINT
            elif event.key == 'f':
                self.mode = Mode.FILL
            elif event.key == 'z':
                self.mode = Mode.PAN_ZOOM
            elif event.key == 'l':
                self.mode = Mode.PICKER

    def on_key_release(self, event):
        """Called whenever key released in canvas.

        Parameters
        ----------
        event : Event
            Vispy event
        """
        if event.key == ' ':
            if self._mode_history != Mode.PAN_ZOOM:
                self.mode = self._mode_history
