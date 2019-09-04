from typing import Union
from xml.etree.ElementTree import Element
import numpy as np
from copy import copy
import vispy.color
from ..base import Layer
from ...util.event import Event
from ..image._constants import Rendering, Interpolation, AVAILABLE_COLORMAPS
from ...util.status_messages import format_float
from ...util.misc import calc_data_range, increment_unnamed_colormap
from vispy.color import get_color_names, Color


class Surface(Layer):
    """
    Surface layer renders meshes onto the canvas.

    Parameters
    ----------
    data : (N, D) array
        Vertices of mesh triangles.
    faces : (M, 3) array of int
        Indices of mesh triangles.
    values : (N,) array
        Values used to color vertices.
    colormap : str, vispy.Color.Colormap, tuple, dict
        Colormap to use for luminance images. If a string must be the name
        of a supported colormap from vispy or matplotlib. If a tuple the
        first value must be a string to assign as a name to a colormap and
        the second item must be a Colormap. If a dict the key must be a
        string to assign as a name to a colormap and the value must be a
        Colormap.
    contrast_limits : list (2,)
        Color limits to be used for determining the colormap bounds for
        luminance images. If not passed is calculated as the min and max of
        the image.
    name : str
        Name of the layer.
    metadata : dict
        Layer metadata.
    scale : tuple of float
        Scale factors for the layer.
    translate : tuple of float
        Translation values for the layer.
    opacity : float
        Opacity of the layer visual, between 0.0 and 1.0.
    blending : str
        One of a list of preset blending modes that determines how RGB and
        alpha values of the layer visual get mixed. Allowed values are
        {'opaque', 'translucent', and 'additive'}.
    visible : bool
        Whether the layer visual is currently being displayed.

    Attributes
    ----------
    data : (N, D) array
        Vertices of mesh triangles.
    faces : (M, 3) array of int
        Indices of mesh triangles.
    values : (N,) array
        Values used to color vertices.
    colormap : str, vispy.Color.Colormap, tuple, dict
        Colormap to use for luminance images. If a string must be the name
        of a supported colormap from vispy or matplotlib. If a tuple the
        first value must be a string to assign as a name to a colormap and
        the second item must be a Colormap. If a dict the key must be a
        string to assign as a name to a colormap and the value must be a
        Colormap.
    contrast_limits : list (2,)
        Color limits to be used for determining the colormap bounds for
        luminance images. If not passed is calculated as the min and max of
        the image.

    Extended Summary
    ----------
    _data_view : (M, 2, 2) array
        The start point and projections of N vectors in 2D for vectors whose
        start point is in the currently viewed slice.
    _mesh_vertices : (4N, 2) array
        The four corner points for the mesh representation of each vector as as
        rectangle in the slice that it starts in.
    _mesh_triangles : (2N, 3) array
        The integer indices of the `_mesh_vertices` that form the two triangles
        for the mesh representation of the vectors.
    """

    _colormaps = AVAILABLE_COLORMAPS

    def __init__(
        self,
        data,
        *,
        faces,
        values,
        colormap='gray',
        contrast_limits=None,
        name=None,
        metadata=None,
        scale=None,
        translate=None,
        opacity=1,
        blending='translucent',
        visible=True,
    ):

        ndim = data.shape[1]

        super().__init__(
            ndim,
            name=name,
            metadata=metadata,
            scale=scale,
            translate=translate,
            opacity=opacity,
            blending=blending,
            visible=visible,
        )

        self.events.add(
            contrast_limits=Event,
            colormap=Event,
            interpolation=Event,
            rendering=Event,
        )

        # Save the vector style params
        # Set contrast_limits and colormaps
        self._colormap_name = ''
        self._contrast_limits_msg = ''
        if contrast_limits is None:
            self._contrast_limits_range = calc_data_range(values)
        else:
            self._contrast_limits_range = contrast_limits
        self._contrast_limits = copy(self._contrast_limits_range)
        self.colormap = colormap
        self.contrast_limits = self._contrast_limits

        # Data containing vectors in the currently viewed slice
        self._data_view = np.zeros((0, self.dims.ndisplay))
        self._view_faces = np.zeros((0, 3))

        # assign mesh data and establish default behavior
        self._values = values
        self._faces = faces
        self.data = data

    @property
    def data(self) -> np.ndarray:
        return self._data

    @data.setter
    def data(self, data: np.ndarray):
        """Array of vertices of mesh triangles."""

        self._data = data

        self._update_dims()
        self.events.data()

    @property
    def values(self) -> np.ndarray:
        return self._values

    @values.setter
    def values(self, values: np.ndarray):
        """Array of values used to color vertices.."""

        self._values = values

        self._set_view_slice()
        self.events.data()

    @property
    def faces(self) -> np.ndarray:
        return self._faces

    @faces.setter
    def faces(self, faces: np.ndarray):
        """Array of indices of mesh triangles.."""

        self.faces = faces

        self._set_view_slice()
        self.events.data()

    def _get_ndim(self):
        """Determine number of dimensions of the layer."""
        return self.data.shape[1]

    def _get_extent(self):
        """Determine ranges for slicing given by (min, max, step)."""
        if len(self.data) == 0:
            maxs = np.ones(self.data.shape[1], dtype=int)
            mins = np.zeros(self.data.shape[1], dtype=int)
        else:
            maxs = np.max(self.data, axis=0)
            mins = np.min(self.data, axis=0)

        return [(min, max, 1) for min, max in zip(mins, maxs)]

    @property
    def colormap(self):
        """2-tuple of str, vispy.color.Colormap: colormap for luminance images.
        """
        return self._colormap_name, self._cmap

    @colormap.setter
    def colormap(self, colormap):
        name = '[unnamed colormap]'
        if isinstance(colormap, str):
            name = colormap
        elif isinstance(colormap, tuple):
            name, cmap = colormap
            self._colormaps[name] = cmap
        elif isinstance(colormap, dict):
            self._colormaps.update(colormap)
            name = list(colormap)[0]  # first key in dict
        elif isinstance(colormap, vispy.color.Colormap):
            name = increment_unnamed_colormap(
                name, list(self._colormaps.keys())
            )
            self._colormaps[name] = colormap
        else:
            warnings.warn(f'invalid value for colormap: {colormap}')
            name = self._colormap_name
        self._colormap_name = name
        self._cmap = self._colormaps[name]
        self._update_thumbnail()
        self.events.colormap()

    @property
    def colormaps(self):
        """tuple of str: names of available colormaps."""
        return tuple(self._colormaps.keys())

    @property
    def contrast_limits(self):
        """list of float: Limits to use for the colormap."""
        return list(self._contrast_limits)

    @contrast_limits.setter
    def contrast_limits(self, contrast_limits):
        self._contrast_limits_msg = (
            format_float(contrast_limits[0])
            + ', '
            + format_float(contrast_limits[1])
        )
        self.status = self._contrast_limits_msg
        self._contrast_limits = contrast_limits
        if contrast_limits[0] < self._contrast_limits_range[0]:
            self._contrast_limits_range[0] = copy(contrast_limits[0])
        if contrast_limits[1] > self._contrast_limits_range[1]:
            self._contrast_limits_range[1] = copy(contrast_limits[1])
        self._update_thumbnail()
        self.events.contrast_limits()

    def _set_view_slice(self):
        """Sets the view given the indices to slice with."""

        not_disp = list(self.dims.not_displayed)
        disp = list(self.dims.displayed)
        indices = np.array(self.dims.indices)

        self._data_view = self.data[:, disp]
        if len(self.data) == 0:
            self._view_faces = np.zeros((0, 3))
        elif self.ndim > self.dims.ndisplay:
            vertices = self.data[:, not_disp].astype('int')
            triangles = vertices[self.faces]
            matches = np.all(triangles == indices[not_disp], axis=(1, 2))
            matches = np.where(matches)[0]
            if len(matches) == 0:
                self._view_faces = np.zeros((0, 3))
            else:
                self._view_faces = self.faces[matches]
        else:
            self._view_faces = self.faces

        self._update_thumbnail()
        self._update_coordinates()
        self.events.set_data()

    def _update_thumbnail(self):
        """Update thumbnail with current surface."""
        pass

    def to_xml_list(self):
        """Convert surface to a list of svg xml elements.

        Returns
        ----------
        xml : list
            List of xml elements.
        """
        xml_list = []

        return xml_list

    def get_value(self):
        """Returns coordinates, values, and a string for a given mouse position
        and set of indices.

        Returns
        ----------
        value : int, None
            Value of the data at the coord.
        """

        return None