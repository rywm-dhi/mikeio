import warnings
from typing import Optional, Sequence, Union
import numpy as np
import pandas as pd
from copy import deepcopy

from .base import TimeSeries
from .eum import EUMType, EUMUnit, ItemInfo
from .spatial.geometry import _Geometry
from .spatial.grid_geometry import Grid1D, Grid2D
from .spatial.FM_geometry import GeometryFM, GeometryFMLayered, GeometryFMPointSpectrum
from mikecore.DfsuFile import DfsuFileType
from .spatial.FM_utils import _plot_map
import mikeio.data_utils as du


class _DataArrayPlotter:
    def __init__(self, da: "DataArray") -> None:
        self.da = da

    def __call__(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)

        if self.da.ndim == 1:
            return self._timeseries(self.da.values, fig, ax, **kwargs)

        if self.da.ndim == 2:
            return ax.imshow(self.da.values, **kwargs)

        # if everything else fails, plot histogram
        return self._hist(ax, **kwargs)

    @staticmethod
    def _get_ax(ax=None, figsize=None):
        import matplotlib.pyplot as plt

        if ax is None:
            _, ax = plt.subplots(figsize=figsize)
        return ax

    @staticmethod
    def _get_fig_ax(ax=None, figsize=None):
        import matplotlib.pyplot as plt

        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        else:
            fig = plt.gcf()
        return fig, ax

    def hist(self, ax=None, figsize=None, **kwargs):
        ax = self._get_ax(ax, figsize)
        return self._hist(ax, **kwargs)

    def _hist(self, ax, **kwargs):
        result = ax.hist(self.da.values.ravel(), **kwargs)
        ax.set_xlabel(self._label_txt())
        return result

    def line(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)
        return self._timeseries(self.da.values, fig, ax, **kwargs)

    def _timeseries(self, values, fig, ax, **kwargs):
        if "title" in kwargs:
            title = kwargs.pop("title")
            ax.set_title(title)
        ax.plot(self.da.time, values, **kwargs)
        ax.set_xlabel("time")
        fig.autofmt_xdate()
        ax.set_ylabel(self._label_txt())
        return ax

    def _label_txt(self):
        return f"{self.da.name} [{self.da.unit.name}]"


class _DataArrayPlotterGrid1D(_DataArrayPlotter):
    def __init__(self, da: "DataArray") -> None:
        super().__init__(da)

    def __call__(self, ax=None, figsize=None, **kwargs):
        ax = self._get_ax(ax, figsize)
        return self._lines(ax, **kwargs)

    def timeseries(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)
        return super()._timeseries(self.da.values, fig, ax, **kwargs)

    def imshow(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)
        pos = ax.imshow(self.da.values, **kwargs)
        fig.colorbar(pos, ax=ax, label=self._label_txt())
        return ax

    def pcolormesh(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)
        pos = ax.pcolormesh(
            self.da.geometry.x,
            self.da.time,
            self.da.values,
            shading="nearest",
            **kwargs,
        )
        cbar = fig.colorbar(pos, label=self._label_txt())
        ax.set_xlabel("x")
        ax.set_ylabel("time")
        return ax

    def _lines(self, ax=None, **kwargs):
        if "title" in kwargs:
            title = kwargs.pop("title")
            ax.set_title(title)
        ax.plot(self.da.geometry.x, self.da.values.T, **kwargs)
        ax.set_xlabel("x")
        ax.set_ylabel(self._label_txt())
        return ax


class _DataArrayPlotterGrid2D(_DataArrayPlotter):
    def __init__(self, da: "DataArray") -> None:
        super().__init__(da)

    def __call__(self, ax=None, figsize=None, **kwargs):
        return self.pcolormesh(ax, figsize, **kwargs)

    def contour(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)

        x, y = self._get_x_y()
        values = self._get_first_step_values()

        pos = ax.contour(x, y, np.flipud(values), **kwargs)
        # fig.colorbar(pos, label=self._label_txt())
        ax.clabel(pos, fmt="%1.2f", inline=1, fontsize=9)
        self._set_aspect_and_labels(ax, self.da.geometry.is_geo, y)
        return ax

    def contourf(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)

        x, y = self._get_x_y()
        values = self._get_first_step_values()

        pos = ax.contourf(x, y, np.flipud(values), **kwargs)
        fig.colorbar(pos, label=self._label_txt())
        self._set_aspect_and_labels(ax, self.da.geometry.is_geo, y)
        return ax

    def pcolormesh(self, ax=None, figsize=None, **kwargs):
        fig, ax = self._get_fig_ax(ax, figsize)

        xn, yn = self._get_xn_yn()
        values = self._get_first_step_values()

        pos = ax.pcolormesh(xn, yn, np.flipud(values), **kwargs)
        fig.colorbar(pos, label=self._label_txt())
        self._set_aspect_and_labels(ax, self.da.geometry.is_geo, yn)
        return ax

    def _get_first_step_values(self):
        if self.da.n_timesteps > 1:
            # select first step as default plotting behaviour
            return self.da.values[0]
        else:
            return np.squeeze(self.da.values)

    def _get_x_y(self):
        x = self.da.geometry.x
        y = self.da.geometry.y
        x = x + self.da.geometry._origin[0]
        y = y + self.da.geometry._origin[1]
        return x, y

    def _get_xn_yn(self):
        xn = self.da.geometry._centers_to_nodes(self.da.geometry.x)
        yn = self.da.geometry._centers_to_nodes(self.da.geometry.y)
        xn = xn + self.da.geometry._origin[0]
        yn = yn + self.da.geometry._origin[1]
        return xn, yn

    @staticmethod
    def _set_aspect_and_labels(ax, is_geo, y):
        if is_geo:
            ax.set_xlabel("Longitude [degrees]")
            ax.set_ylabel("Latitude [degrees]")
            mean_lat = np.mean(y)
            ax.set_aspect(1.0 / np.cos(np.pi * mean_lat / 180))
        else:
            ax.set_xlabel("Easting [m]")
            ax.set_ylabel("Northing [m]")
            ax.set_aspect("equal")


class _DataArrayPlotterFM(_DataArrayPlotter):
    def __init__(self, da: "DataArray") -> None:
        super().__init__(da)

    def __call__(self, ax=None, figsize=None, **kwargs):
        ax = self._get_ax(ax, figsize)
        return self._plot_FM_map(ax, **kwargs)

    def contour(self, ax=None, figsize=None, **kwargs):
        ax = self._get_ax(ax, figsize)
        kwargs["plot_type"] = "contour"
        return self._plot_FM_map(ax, **kwargs)

    def contourf(self, ax=None, figsize=None, **kwargs):
        ax = self._get_ax(ax, figsize)
        kwargs["plot_type"] = "contourf"
        return self._plot_FM_map(ax, **kwargs)

    def mesh(self, ax=None, figsize=None, **kwargs):
        return self.da.geometry.plot_mesh(figsize=figsize, ax=ax, **kwargs)

    def outline(self, ax=None, figsize=None, **kwargs):
        return self.da.geometry.plot_outline(figsize=figsize, ax=ax, **kwargs)

    def _plot_FM_map(self, ax, **kwargs):
        if self.da.n_timesteps > 1:
            # select first step as default plotting behaviour
            values = self.da.values[0]
        else:
            values = np.squeeze(self.da.values)

        title = f"{self.da.time[0]}"
        if self.da.geometry.is_2d:
            geometry = self.da.geometry
        else:
            # select surface as default plotting for 3d files
            values = values[self.da.geometry.top_elements]
            geometry = self.da.geometry.geometry2d
            title = "Surface, " + title

        if "label" not in kwargs:
            kwargs["label"] = self._label_txt()
        if "title" not in kwargs:
            kwargs["title"] = title

        return _plot_map(
            node_coordinates=geometry.node_coordinates,
            element_table=geometry.element_table,
            element_coordinates=geometry.element_coordinates,
            boundary_polylines=geometry.boundary_polylines,
            is_geo=geometry.is_geo,
            z=values,
            ax=ax,
            **kwargs,
        )


class DataArray(TimeSeries):

    deletevalue = 1.0e-35

    def __init__(
        self,
        data,
        # *,
        time: Union[pd.DatetimeIndex, str],
        item: ItemInfo = None,
        geometry: _Geometry = None,
        zn=None,
        dims: Optional[Sequence[str]] = None,
    ):
        # TODO: add optional validation validate=True
        self._values = self._parse_data(data)
        self.time = du._parse_time(time)
        if (len(self.time) > 1) and self._values.shape[0] != len(self.time):
            raise ValueError(
                f"Number of timesteps ({self.n_timesteps}) does not fit with data shape {self.values.shape}"
            )
        self.dims = self._parse_dims(dims, geometry)
        self.item = self._parse_item(item)
        self.geometry = self._parse_geometry(geometry, self.dims, self.shape)
        self._zn = self._parse_zn(zn, self.geometry, self.n_timesteps)
        self.plot = self._get_plotter_by_geometry()

    @staticmethod
    def _parse_data(data):
        validation_errors = []
        for p in ("shape", "ndim", "dtype"):
            if not hasattr(data, p):
                validation_errors.append(p)
        if len(validation_errors) > 0:
            raise TypeError(
                "Data must be ArrayLike, e.g. numpy array, but it lacks properties: "
                + ", ".join(validation_errors)
            )
        return data

    def _parse_dims(self, dims, geometry):
        if dims is None:
            return self._guess_dims(self.ndim, self.shape, self.n_timesteps, geometry)
        else:
            if self.ndim != len(dims):
                raise ValueError("Number of named dimensions does not equal data ndim")
            if ("time" in dims) and dims[0] != "time":
                raise ValueError("time must be first dimension if present!")
            if (self.n_timesteps > 1) and ("time" not in dims):
                raise ValueError(
                    f"time missing from named dimensions {dims}! (number of timesteps: {self.n_timesteps})"
                )
            return dims

    @staticmethod
    def _guess_dims(ndim, shape, n_timesteps, geometry):
        # This is not very robust, but is probably a reasonable guess
        time_is_first = (n_timesteps > 1) or (shape[0] == 1 and n_timesteps == 1)
        dims = ["time"] if time_is_first else []
        ndim_no_time = ndim if (len(dims) == 0) else ndim - 1

        if isinstance(geometry, GeometryFMPointSpectrum):
            if ndim_no_time > 0:
                dims.append("frequency")
            if ndim_no_time > 1:
                dims.append("direction")
        elif isinstance(geometry, GeometryFM):
            if geometry._type == DfsuFileType.DfsuSpectral1D:
                if ndim_no_time > 0:
                    dims.append("node")
            else:
                if ndim_no_time > 0:
                    dims.append("element")
            if geometry.is_spectral:
                if ndim_no_time > 1:
                    dims.append("frequency")
                if ndim_no_time > 2:
                    dims.append("direction")
        elif isinstance(geometry, Grid1D):
            dims.append("x")
        elif isinstance(geometry, Grid2D):
            dims.append("y")
            dims.append("x")
        else:
            # gridded
            if ndim_no_time > 2:
                dims.append("z")
            if ndim_no_time > 1:
                dims.append("y")
            if ndim_no_time > 0:
                dims.append("x")
        return tuple(dims)

    @staticmethod
    def _parse_item(item):
        if item is None:
            return ItemInfo("NoName")

        if not isinstance(item, ItemInfo):
            try:
                item = ItemInfo(item)
            except:
                raise ValueError(
                    "Item must be None, ItemInfo or valid input to ItemInfo"
                )
        return item

    @staticmethod
    def _parse_geometry(geometry, dims, shape):
        if len(dims) > 1 and geometry is None:
            # raise ValueError("Geometry is required for ndim >=1")
            warnings.warn("Geometry is required for ndim >=1")

        axis = 1 if "time" in dims else 0
        # dims_no_time = tuple([d for d in dims if d != "time"])
        # shape_no_time = shape[1:] if ("time" in dims) else shape

        if isinstance(geometry, GeometryFMPointSpectrum):
            pass
        elif isinstance(geometry, GeometryFM):
            if geometry.is_spectral:
                if geometry._type == DfsuFileType.DfsuSpectral1D:
                    assert (
                        shape[axis] == geometry.n_nodes
                    ), "data shape does not match number of nodes"
                elif geometry._type == DfsuFileType.DfsuSpectral2D:
                    assert (
                        shape[axis] == geometry.n_elements
                    ), "data shape does not match number of elements"
            else:
                assert (
                    shape[axis] == geometry.n_elements
                ), "data shape does not match number of elements"
        elif isinstance(geometry, Grid1D):
            assert (
                shape[axis] == geometry.n
            ), "data shape does not match number of grid points"
        elif isinstance(geometry, Grid2D):
            assert shape[axis] == geometry.ny, "data shape does not match ny"
            assert shape[axis + 1] == geometry.nx, "data shape does not match nx"
        # elif isinstance(geometry, Grid3D): # TODO

        return geometry

    @staticmethod
    def _parse_zn(zn, geometry, n_timesteps):
        if zn is not None:
            if isinstance(geometry, GeometryFMLayered):
                # TODO: np.squeeze(zn) if n_timesteps=1 ?
                if (n_timesteps > 1) and (zn.shape[0] != n_timesteps):
                    raise ValueError(
                        f"zn has wrong shape ({zn.shape}). First dimension should be of size n_timesteps ({n_timesteps})"
                    )
                if zn.shape[-1] != geometry.n_nodes:
                    raise ValueError(
                        f"zn has wrong shape ({zn.shape}). Last dimension should be of size n_nodes ({geometry.n_nodes})"
                    )
            else:
                raise ValueError("zn can only be provided for layered dfsu data")
        return zn

    def _get_plotter_by_geometry(self):
        if isinstance(self.geometry, GeometryFM):
            return _DataArrayPlotterFM(self)
        elif isinstance(self.geometry, Grid1D):
            return _DataArrayPlotterGrid1D(self)
        elif isinstance(self.geometry, Grid2D):
            return _DataArrayPlotterGrid2D(self)
        else:
            return _DataArrayPlotter(self)

    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, value):
        if value.shape != self._values.shape:
            raise ValueError("Shape of new data is wrong")

        self._values = value

    def __setitem__(self, key, value):
        # TODO: use .values instead?
        if du._is_boolean_mask(key):
            mask = key if isinstance(key, np.ndarray) else key.values
            return du._set_by_boolean_mask(self._values, mask, value)
        self._values[key] = value

    def __getitem__(self, key) -> "DataArray":
        if du._is_boolean_mask(key):
            mask = key if isinstance(key, np.ndarray) else key.values
            return du._get_by_boolean_mask(self.values, mask)

        dims = self.dims
        if "time" in dims:
            steps = key[0] if isinstance(key, tuple) else key
            space_key = key[1:] if isinstance(key, tuple) else None

            # select in time
            steps = du._get_time_idx_list(self.time, steps)
            time = self.time[steps]
            if len(steps) == 1:
                dims = tuple([d for d in dims if d != "time"])

            key = (steps, *space_key) if isinstance(key, tuple) else steps
        else:
            time = self.time
            steps = None
            space_key = key

        # select in space
        geometry = self.geometry
        zn = self._zn
        if space_key is not None:
            if isinstance(self.geometry, GeometryFM):
                # TODO: allow for selection of layers
                elements = space_key[0] if isinstance(space_key, tuple) else space_key
                if isinstance(elements, slice):
                    elements = list(range(*elements.indices(self.geometry.n_elements)))
                else:
                    elements = np.atleast_1d(elements)
                if len(elements) == 1:
                    geometry = None
                    zn = None
                    dims = tuple([d for d in dims if d != "element"])
                else:
                    geometry = self.geometry.elements_to_geometry(elements)

                if isinstance(self.geometry, GeometryFMLayered):
                    if isinstance(geometry, GeometryFMLayered):
                        nodes = self.geometry.element_table[elements]
                        unodes = np.unique(np.hstack(nodes))
                        zn = self._zn[:, unodes]
                    else:
                        zn = None

                key = elements if (steps is None) else (steps, elements)
            else:
                # TODO: better handling of dfs1,2,3
                key = space_key if (steps is None) else (steps, *space_key)

        data = self._values[key]  # .copy()
        return DataArray(
            data=np.squeeze(data),
            time=time,
            item=self.item,
            geometry=geometry,
            zn=zn,
            dims=dims,
        )

    def _is_compatible(self, other, raise_error=False):
        """check if other DataArray has equivalent dimensions, time and geometry"""
        problems = []
        if not isinstance(other, DataArray):
            return False
        if self.shape != other.shape:
            problems.append("shape of data must be the same")
        if self.n_timesteps != other.n_timesteps:
            problems.append("Number of timesteps must be the same")
        if self.start_time != self.start_time:
            problems.append("start_time must be the same")
        if type(self.geometry) != type(other.geometry):
            problems.append("The type of geometry must be the same")
        if hasattr(self.geometry, "__eq__"):
            if not (self.geometry == self.geometry):
                problems.append("The geometries must be the same")
        if self._zn is not None:
            # it can be expensive to check equality of zn
            # so we test only size, first and last element
            if (
                other._zn is None
                or self._zn.shape != other._zn.shape
                or self._zn.ravel()[0] != other._zn.ravel()[0]
                or self._zn.ravel()[-1] != other._zn.ravel()[-1]
            ):
                problems.append("zn must be the same")

        if self.dims != other.dims:
            problems.append("Dimension names (dims) must be the same")

        if raise_error:
            raise ValueError("".join(problems))

        return len(problems) == 0

    @staticmethod
    def _other_to_values(other):
        return other.values if isinstance(other, DataArray) else other

    def _boolmask_to_new_DataArray(self, bmask):
        return DataArray(
            data=bmask,
            time=self.time,
            item=ItemInfo("Boolean"),
            geometry=self.geometry,
            zn=self._zn,
        )

    def __lt__(self, other):
        bmask = self.values < self._other_to_values(other)
        return self._boolmask_to_new_DataArray(bmask)

    def __gt__(self, other):
        bmask = self.values > self._other_to_values(other)
        return self._boolmask_to_new_DataArray(bmask)

    def __le__(self, other):
        bmask = self.values <= self._other_to_values(other)
        return self._boolmask_to_new_DataArray(bmask)

    def __ge__(self, other):
        bmask = self.values >= self._other_to_values(other)
        return self._boolmask_to_new_DataArray(bmask)

    def __eq__(self, other):
        bmask = self.values == self._other_to_values(other)
        return self._boolmask_to_new_DataArray(bmask)

    def __ne__(self, other):
        bmask = self.values != self._other_to_values(other)
        return self._boolmask_to_new_DataArray(bmask)

    def to_numpy(self) -> np.ndarray:
        return self._values

    def flipud(self) -> "DataArray":
        """Flip upside down"""

        self.values = np.flip(self.values, axis=1)
        return self

    def _to_dataset(self) -> "Dataset":
        """Create a single-item dataset"""
        from mikeio import Dataset

        return Dataset(
            {self.name: self}
        )  # Single-item Dataset (All info is contained in the DataArray, no need for additional info)

    def to_dfs(self, filename) -> None:
        self._to_dataset().to_dfs(filename)

    def max(self, axis="time") -> "DataArray":
        """Max value along an axis

        Parameters
        ----------
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0

        Returns
        -------
        DataArray
            array with max values

        See Also
        --------
            nanmax : Max values with NaN values removed
        """
        return self.aggregate(axis=axis, func=np.max)

    def min(self, axis="time") -> "DataArray":
        """Min value along an axis

        Parameters
        ----------
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0

        Returns
        -------
        DataArray
            array with min values

        See Also
        --------
            nanmin : Min values with NaN values removed
        """
        return self.aggregate(axis=axis, func=np.min)

    def mean(self, axis="time") -> "DataArray":
        """Mean value along an axis

        Parameters
        ----------
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0

        Returns
        -------
        DataArray
            array with mean values

        See Also
        --------
            nanmean : Mean values with NaN values removed
        """
        return self.aggregate(axis=axis, func=np.mean)

    def nanmax(self, axis="time") -> "DataArray":
        """Max value along an axis (NaN removed)

        Parameters
        ----------
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0

        Returns
        -------
        DataArray
            array with max values

        See Also
        --------
            nanmax : Max values with NaN values removed
        """
        return self.aggregate(axis=axis, func=np.nanmax)

    def nanmin(self, axis="time") -> "DataArray":
        """Min value along an axis (NaN removed)

        Parameters
        ----------
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0

        Returns
        -------
        DataArray
            array with min values

        See Also
        --------
            nanmin : Min values with NaN values removed
        """
        return self.aggregate(axis=axis, func=np.nanmin)

    def nanmean(self, axis="time") -> "DataArray":
        """Mean value along an axis (NaN removed)

        Parameters
        ----------
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0

        Returns
        -------
        DataArray
            array with mean values

        See Also
        --------
            mean : Mean values
        """
        return self.aggregate(axis=axis, func=np.nanmean)

    def aggregate(self, axis="time", func=np.nanmean, **kwargs) -> "DataArray":
        """Aggregate along an axis

        Parameters
        ----------
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0
        func: function, optional
            default np.nanmean

        Returns
        -------
        DataArray
            dataarray with aggregated values

        See Also
        --------
            max : Max values
            nanmax : Max values with NaN values removed
        """

        axis = du._parse_axis(self.shape, self.dims, axis)
        time = du._time_by_agg_axis(self.time, axis)

        dims = tuple([d for i, d in enumerate(self.dims) if i != axis])

        data = func(self.to_numpy(), axis=axis, keepdims=False, **kwargs)

        if axis == 0:
            geometry = self.geometry
        else:
            geometry = None
        return DataArray(
            data=data, time=time, item=self.item, geometry=geometry, dims=dims
        )

    def quantile(self, q, *, axis="time", **kwargs):
        """Compute the q-th quantile of the data along the specified axis.

        Wrapping np.quantile

        Parameters
        ----------
        q: array_like of float
            Quantile or sequence of quantiles to compute,
            which must be between 0 and 1 inclusive.
        axis: (int, str, None), optional
            axis number or "time" or "space", by default "time"=0

        Returns
        -------
        DataArray
            data with quantile values

        Examples
        --------
        >>> da.quantile(q=[0.25,0.75])
        >>> da.quantile(q=0.5)
        >>> da.quantile(q=[0.01,0.5,0.99], axis="space")

        See Also
        --------
        nanquantile : quantile with NaN values ignored
        """
        return self._quantile(q, axis=axis, func=np.quantile, **kwargs)

    def isel(self, idx, axis=1):
        """
        Select subset along an axis.

        Parameters
        ----------
        idx: int, scalar or array_like
        axis: (int, str, None), optional
            axis number or "time", by default 1

        Returns
        -------
        DataArray
            data with subset

        """

        axis = du._parse_axis(self.shape, self.dims, axis)
        if axis == 0:
            time = self.time[idx]
            item = self.item
            geometry = self.geometry
            zn = self._zn[idx] if self._zn else None
        else:
            time = self.time
            item = self.item
            geometry = None  # TODO
            if hasattr(self.geometry, "isel"):
                spatial_axis = du._axis_to_spatial_axis(self.dims, axis)
                geometry = self.geometry.isel(idx, axis=spatial_axis)
            zn = None  # TODO

        x = np.take(self.values, idx, axis=axis)

        dims = tuple(
            [d for i, d in enumerate(self.dims) if i != axis]
        )  # TODO we will need this in many places

        return DataArray(
            data=x,
            time=time,
            item=item,
            geometry=geometry,
            zn=zn,
            dims=dims,
        )

    def _quantile(self, q, *, axis=0, func=np.quantile, **kwargs):

        axis = du._parse_axis(self.shape, self.dims, axis)
        time = du._time_by_agg_axis(self.time, axis)

        if not np.isscalar(q):
            raise NotImplementedError()

        qdat = func(self.values, q=q, axis=axis, **kwargs)

        geometry = deepcopy(self.geometry)
        if axis != 0:
            geometry = None

        dims = tuple(
            [d for i, d in enumerate(self.dims) if i != axis]
        )  # TODO we will need this in many places
        return DataArray(qdat, time, item=self.item, geometry=geometry, dims=dims)

    def __radd__(self, other):
        return self.__add__(other)

    def __add__(self, other):
        if isinstance(other, self.__class__):
            return self._add_dataarray(other)
        else:
            return self._add_value(other)

    def __rsub__(self, other):
        ds = self.__mul__(-1.0)
        return other + ds

    def __sub__(self, other):
        if isinstance(other, self.__class__):
            return self._add_dataarray(other, sign=-1.0)
        else:
            return self._add_value(-other)

    def __rmul__(self, other):
        return self.__mul__(other)

    def __mul__(self, other):
        if isinstance(other, self.__class__):
            raise ValueError("Multiplication is not possible for two DataArrays")
        else:
            return self._multiply_value(other)

    def _add_dataarray(self, other, sign=1.0):
        # self._check_datasets_match(other) # TODO
        try:
            data = self.values + sign * other.values
        except:
            raise ValueError("Could not add data")

        new_da = self.copy()

        new_da.values = data

        return new_da

    def _add_value(self, value):
        try:
            data = value + self.values
        except:
            raise ValueError(f"{value} could not be added to DataArray")

        new_da = self.copy()

        new_da.values = data

        return new_da

    def _multiply_value(self, value):
        try:
            data = value * self.values
        except:
            raise ValueError(f"{value} could not be multiplied to DataArray")
        new_da = self.copy()

        new_da.values = data

        return new_da

    def copy(self):

        return deepcopy(self)

    @property
    def name(self) -> Optional[str]:
        if self.item.name:
            return self.item.name
        else:
            return None

    @name.setter
    def name(self, value):
        self.item.name = value

    @property
    def type(self) -> EUMType:
        return self.item.type

    @property
    def unit(self) -> EUMUnit:
        return self.item.unit

    @property
    def start_time(self):
        """First time instance (as datetime)"""
        return self.time[0].to_pydatetime()

    @property
    def end_time(self):
        """Last time instance (as datetime)"""
        return self.time[-1].to_pydatetime()

    @property
    def is_equidistant(self):
        """Is Dataset equidistant in time?"""
        if len(self.time) < 3:
            return True
        return len(self.time.to_series().diff().dropna().unique()) == 1

    @property
    def timestep(self):
        """Time step in seconds if equidistant (and at
        least two time instances); otherwise None
        """
        dt = None
        if len(self.time) > 1:
            if self.is_equidistant:
                dt = (self.time[1] - self.time[0]).total_seconds()
        return dt

    @property
    def n_timesteps(self) -> int:
        """Number of time steps"""
        return len(self.time)

    @property
    def n_items(self) -> int:
        """Number of items"""
        return 1

    @property
    def items(self) -> Sequence[ItemInfo]:  # Sequence with a single element!
        return [self.item]

    @property
    def shape(self):
        return self.values.shape

    @property
    def ndim(self):
        return self.values.ndim

    @property
    def dtype(self):
        return self.values.dtype

    def __repr__(self):

        out = ["<mikeio.DataArray>"]
        if self.name is not None:
            out.append(f"Name: {self.name}")
        if isinstance(self.geometry, GeometryFM):
            gtxt = f"Geometry: {self.geometry.type_name}"
            if self.geometry.is_layered:
                n_z_layers = (
                    "no"
                    if self.geometry.n_z_layers is None
                    else self.geometry.n_z_layers
                )
                gtxt += f" ({self.geometry.n_sigma_layers} sigma-layers, {n_z_layers} z-layers)"

            out.append(gtxt)

        dims = [f"{self.dims[i]}:{self.shape[i]}" for i in range(self.ndim)]
        dimsstr = ", ".join(dims)
        out.append(f"Dimensions: ({dimsstr})")

        timetxt = (
            f"Time: {self.time[0]} (time-invariant)"
            if self.n_timesteps == 1
            else f"Time: {self.time[0]} - {self.time[-1]} ({self.n_timesteps} records)"
        )
        out.append(timetxt)

        if not self.is_equidistant:
            out.append("-- Non-equidistant calendar axis --")

        return str.join("\n", out)
