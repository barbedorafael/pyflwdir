# -*- coding: utf-8 -*-
# Author: Dirk Eilander (contact: dirk.eilander@deltares.nl)
# August 2019

from numba import njit, vectorize
import numpy as np

from pyflwdir import core

# D8 type
_ds = np.array([
    [32, 64, 128], 
    [16, 0,  1], 
    [8,  4,  2]], dtype=np.uint8)
_us = np.array([
    [2,   4,  8], 
    [1,   0,  16], 
    [128, 64, 32]], dtype=np.uint8)
_mv = np.uint8(247)
_pv = np.array([0, 255], dtype=np.uint8)
_d8_ = np.unique(np.concatenate([_pv, np.array([_mv]), _ds.flatten()]))

# convert between 1D ds index and 2D D8 network
@njit()
def parse_d8(flwdir, _max_depth = 8):
    size = flwdir.size
    ncol = flwdir.shape[1]
    flwdir_flat = flwdir.ravel()
    # keep valid indices only
    idxs_valid = np.where(flwdir.ravel()!=_mv)[0].astype(np.uint32)
    n = idxs_valid.size
    idxs_inv = np.ones(size, np.uint32)*core._mv
    idxs_inv[idxs_valid] = np.array([i for i in range(n)], dtype=np.uint32)
    # allocate output arrays
    pits_lst = []
    idxs_ds = np.ones(n, dtype=np.uint32)*core._mv
    idxs_us = np.ones((n, _max_depth), dtype=np.uint32)*core._mv
    _max_us = 0
    i = np.uint32(0)
    for i in range(n):
        idx0 = idxs_valid[i]
        dd = flwdir_flat[idx0]
        dr, dc = drdc(dd)
        if dr==0 and dc==0:
            idxs_ds[i] = i
            pits_lst.append(np.uint32(i))
        else:
            idx_ds = idx0 + dc + dr*ncol
            ids = idxs_inv[idx_ds]
            if ids == core._mv:
                raise ValueError('d8 not valid')
            idxs_ds[i] = ids
            for ii in range(_max_depth):
                if idxs_us[ids,ii] == core._mv:
                    idxs_us[ids,ii] = i
                    break
            if ii >  _max_us:
                _max_us = ii
    idxs_us = idxs_us[:, :_max_depth]
    return idxs_valid, idxs_ds, idxs_us, np.array(pits_lst)


# core d8 functions 
def _is_d8(flwdir):
    return np.all([v in _d8_ for v in np.unique(flwdir)])

@vectorize(["boolean(uint8)"])
def ispit(dd):
    return np.any(dd == _pv)

@njit 
def isnodata(dd):
    return dd == _mv

@njit("Tuple((int8, int8))(uint8)")
def drdc(dd):
    dr, dc = np.int8(0), np.int8(0)
    if dd >= np.uint8(16) and dd <= np.uint8(128): 
        if dd == np.uint8(16): #west
            dr, dc = np.int8(0), np.int8(-1)
        else: # north
            dr = np.int8(-1)
            dc = np.int8(np.log2(dd) - 6)
    elif dd < np.uint8(16):
        if dd >= np.uint8(2): # south
            dr = np.int8(1)
            dc = np.int8(-1 * (np.log2(dd) - 2))
        else: # pit / #east
            dr = np.int8(0)
            dc = np.int8(dd)
    return dr, dc

@njit
def ds_index(idx0, flwdir_flat, shape, dd=_mv):
    """returns numpy array (int64) with indices of donwstream neighbors on a D8 grid.
    At a pit the current index is returned
    
    D8 format
    1:E 2:SE, 4:S, 8:SW, 16:W, 32:NW, 64:N, 128:NE, 0:mouth, -1/255: inland pit, -9/247: undefined (ocean)
    """
    nrow, ncol = shape
    # FIXME: i don't like this extra if statement. can we do this differently?
    if dd == _mv:
        dd = flwdir_flat[idx0]
    r0 = idx0 // ncol
    c0 = idx0 %  ncol
    dr, dc = drdc(dd)
    idx = np.int64(-1)
    if not (r0 == 0 and dr == -1) and not (c0 == 0 and dc == -1)\
        and not (r0 == nrow-1 and dr == 1) and not (c0 == ncol-1 and dc == 1):
        idx = idx0 + dc + dr*ncol
    return idx

@njit
def us_indices(idx0, flwdir_flat, shape):
    """returns a numpy array (uint32) with indices of upstream neighbors on a D8 grid
    if it leaves the domain a negative D8 value indicating the side where it leaves the domain is returned"""
    nrow, ncol = shape
    # assume c-style row-major
    r = idx0 // ncol
    c = idx0 %  ncol
    idx = np.int64(-1)
    us_idxs = list()
    for dr in range(-1, 2):
        row = r + dr
        for dc in range(-1, 2):
            col = c + dc
            if dr == 0 and dc == 0: # skip pit -> return empty array
                continue
            elif row >= 0 and row < nrow and col >= 0 and col < ncol: # check bounds
                idx = row*ncol + col
                if flwdir_flat[idx] == _us[dr+1, dc+1]:
                    us_idxs.append(idx)
    return np.array(us_idxs)

@njit
def idx_to_dd(idx0, idx_ds, shape):
    """returns local D8 flow direction based on current and downstream index"""
    ncol = shape[1]
    # size = nrow * ncol
    # assert idx0 < size and idx_ds < size
    r = (idx_ds // ncol) - (idx0 // ncol) + 1
    c = (idx_ds %  ncol) - (idx0 %  ncol) + 1
    dd = _mv
    if r >= 0 and r < 3 and c >= 0 and c < 3:
        dd = _ds[r, c]
    return dd

# @njit
# def pit_indices(flwdir_flat):
#     idxs = []
#     for idx0 in range(flwdir_flat.size):
#         if np.any(flwdir_flat[idx0] == _pv):
#             idxs.append(idx0)
#     return np.array(idxs, dtype=np.int64)
#
# # @njit
# def isdir(dd):
#     return np.any(dd == _ds)
#
# @njit
# def us_main_indices(idx0, flwdir_flat, uparea_flat, shape, upa_min):
#     """returns the index (uint32) of the upstream cell with the largest uparea"""
#     nrow, ncol = shape
#     # assume c-style row-major
#     r = idx0 // ncol
#     c = idx0 % ncol
#     idx = np.int64(-1)
#     us_upa = uparea_flat[idx0]
#     idx_lst = list()
#     upa_lst = list()
#     if us_upa >= upa_min:
#         us_upa = upa_min
#         for dr in range(-1, 2):
#             row = r + dr
#             for dc in range(-1, 2):
#                 col = c + dc
#                 if dr == 0 and dc == 0: # skip pit -> return empty array
#                     continue
#                 elif row >= 0 and row < nrow and col >= 0 and col < ncol: # check bounds
#                     idx = row*ncol + col
#                     if flwdir_flat[idx] == _us[dr+1, dc+1]:
#                         upa = uparea_flat[idx]
#                         if upa >= us_upa:
#                             us_upa = upa
#                             idx_lst.append(idx)
#                             upa_lst.append(upa)
#     us_idxs = np.array(idx_lst)
#     if us_idxs.size > 1:
#         upas = np.array(upa_lst)
#         us_idxs = us_idxs[upas>=us_upa]
#     return us_idxs, us_upa
