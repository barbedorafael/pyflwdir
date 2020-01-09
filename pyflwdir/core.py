# -*- coding: utf-8 -*-
# Author: Dirk Eilander (contact: dirk.eilander@deltares.nl)
# August 2019

"""Core upstream / downstream functionality based on parsed indices from core_xxx.py submules"""

from numba import njit, prange
from numba.typed import List
import numpy as np

_mv = np.uint32(-1)

#### NETWORK TREE ####
@njit
def network_tree(idxs_pits, idxs_us):
    """Set drainage direction network tree ordering cells from 
    downstream to upstream
    
    Parameters
    ----------
    idxs_pit, idxs_us : ndarray of int
        internal indices of pit, downstream, upstream cells

    Returns
    -------
    Sorted 1D arrays with internal indices : List of arrays 
    """
    tree = List()
    tree.append(idxs_pits)
    idxs = idxs_pits
    # move upstream
    while True:
        idxs_us0 = upstream(idxs, idxs_us)
        if idxs_us0.size == 0:    # break if no more upstream
            break
        tree.append(idxs_us0)     # append next leave to tree
        idxs = idxs_us0           # next loop
    return tree                   # down- to upstream

#### UPSTREAM / DOWNSTREAM functions ####
@njit
def upstream(idx0, idxs_us):
    """Returns the internal upstream indices.
    
    Parameters
    ----------
    idx0 : array_like of int
        index of local cell(s)
    idxs_us : ndarray of int
        internal indices of upstream cells

    Returns
    -------
    1D array of internal upstream indices : ndarray of int  
    """
    idxs_us0 = idxs_us[idx0, :].ravel()
    return idxs_us0[idxs_us0 != _mv]

@njit
def _main_upstream(idx0, idxs_us, uparea_flat, upa_min = 0):
    """Returns the index of the upstream cell with the largest uparea"""
    idx_us0 = _mv
    upa0 = upa_min
    for idx_us in upstream(idx0, idxs_us):
        if uparea_flat[idx_us] > upa0:
            idx_us0 = idx_us
            upa0 = uparea_flat[idx_us]
    return idx_us0

@njit
def main_upstream(idxs, idxs_us, uparea_flat, upa_min = 0):
    """Returns the index of the upstream cell with the largest uparea
    
    Parameters
    ----------
    idxs : ndarray of int
        internal indices of local cells
    idxs_us : ndarray of int
        internal indices of upstream cells
    uparea_flat : ndarray
        1D array with upstream area values
    upa_min : float, optional 
        minimum upstream area for upstream cell to be considered
    

    Returns
    -------
    1D array of internal upstream indices : ndarray of int  
    """
    if idxs_us.shape[0] != uparea_flat.size:
        raise ValueError('uparea_flat has invalid size')
    idxs_us_main = np.ones(idxs.size, dtype=idxs_us.dtype)*_mv
    for i in range(idxs.size):
        idxs_us_main[i] = _main_upstream(idxs[i], idxs_us, uparea_flat, upa_min = upa_min)
    return idxs_us_main

@njit
def downstream(idx0, idxs_ds):
    """Returns the internal downstream indices.
    
    Parameters
    ----------
    idx0 : array_like of int
        index of local cell(s)
    idxs_ds : ndarray of int
        internal indices of downstream cells

    Returns
    -------
    1D array of internal downstream indices : ndarray of int  
    """
    return idxs_ds[idx0]

@njit
def _downstream_river(idx0, idxs_ds, river_flat):
    """Return index of nearest downstream river cell for single index"""
    at_stream = river_flat[idx0]
    while not at_stream:
        idx_ds = idxs_ds[idx0]
        if idx_ds == idx0 or idx_ds == _mv: 
            break
        idx0 = idx_ds
        at_stream = river_flat[idx0]
    return idx0

@njit
def downstream_river(idxs0, idxs_ds, river_flat):
    """Returns the next downstream index which is located on a river cell.
    
    Parameters
    ----------
    idxs0 : ndarray of in
        index of local cell(s)
    idxs_ds : ndarray of int
        internal indices of upstream cells
    data : ndarray of bool
        True if stream cell

    Returns
    -------
    1D array of internal downstream stream indices : ndarray of int  
    """
    
    idx_out = np.zeros(idxs0.size, dtype=np.uint32)
    for i in range(idxs0.size):
        idx_out[i] = _downstream_river(np.uint32(idxs0[i]), idxs_ds, river_flat)
    return idx_out

#### PIT / LOOP INDICES ####
@njit
def pit_indices(idxs_ds):
    """Returns the internal pit indices, i.e. where the 
    downstream cell is equal to the local cell.
    
    Parameters
    ----------
    idxs_ds : ndarray of int
        internal indices of downstream cells

    Returns
    -------
    1D array of internal downstream indices : ndarray of int  
    """
    idx_lst = []
    for idx0 in range(idxs_ds.size):
        if idx0 == idxs_ds[idx0]:
            idx_lst.append(idx0)
    return np.array(idx_lst, dtype=idxs_ds.dtype)

@njit
def loop_indices(idxs_ds, idxs_us):
    """Returns the internal loop indices, i.e. for cells
    which do not have a pit at its most downstream end.
    
    Parameters
    ----------
    idxs_ds, idxs_us : ndarray of int
        internal indices of pit, downstream, upstream cells

    Returns
    -------
    1D array of internal loop indices : array_like  
    """
    # internal lists
    no_loop = idxs_ds == _mv
    idxs_ds0 = pit_indices(idxs_ds)
    if idxs_ds0.size > 0: # no valid cells!
        no_loop[idxs_ds0] = True 
    # loop over pits and mark upstream area
    while True:
        idxs_us0 = upstream(idxs_ds0, idxs_us)
        if idxs_us0.size == 0: 
            break
        no_loop[idxs_us0] = ~no_loop[idxs_us0]
        idxs_ds0 = idxs_us0 # next iter
    return np.where(~no_loop)[0]

#### internal data indexing and reordering functions ####
@njit
def _internal_idx(idxs, idxs_valid, size):
    """Convert 1D index to internal 1D index (valid cells only).
    
    Parameters
    ----------
    idxs : ndarray of int
        1D flwdir raster index
    idxs_valid : ndarray of int
        1D flwdir raster indices of valid cells
    size : int
        size of flwdir raster

    Returns
    -------
    1D internal index : ndarray of int    
    """
    idxs_inv = np.ones(size, idxs_valid.dtype)*_mv
    idxs_inv[idxs_valid] = np.array([i for i in range(idxs_valid.size)], dtype=idxs_valid.dtype)
    return idxs_inv[idxs]

@njit
def _reshape(data, idxs_valid, shape, nodata=-9999):
    """Reshape 1D data with same size as internal index to a 2D raster
    with the data placed at the internal index.
    
    Parameters
    ----------
    data : ndarray
        1D data
    idxs_valid : ndarray of int
        1D flwdir raster indices of valid cells
    shape : tuple of int
        shape of output raster

    Returns
    -------
    2D raster data : ndarray    
    """
    if idxs_valid.size != data.size:
        raise ValueError('data has invalid size')
    data_out = np.ones(shape[0]*shape[1], dtype=data.dtype)*nodata
    data_out[idxs_valid] = data
    return data_out.reshape(shape)