#!/usr/bin/env pytest
###############################################################################
# $Id$
#
# Project:  GDAL/OGR Test Suite
# Purpose:  ARG Testing.
# Author:   David Zwarg <dzwarg@azavea.com>
#
###############################################################################
# Copyright (c) 2012, David Zwarg <dzwarg@azavea.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
###############################################################################

import os
import struct
from copy import copy

import gdaltest
import pytest

from osgeo import gdal

pytestmark = [
    pytest.mark.require_driver("ARG"),
    pytest.mark.random_order(disabled=True),
]

# given fmt and nodata, encodes a value as bytes

###############################################################################
@pytest.fixture(autouse=True, scope="module")
def module_disable_exceptions():
    with gdaltest.config_option("GDAL_ENABLE_DEPRECATED_DRIVER_ARG", "YES"):
        yield


def pack(fmt, nodata, value):
    if value is None:
        value = nodata
    return struct.pack(fmt, value)


# packs the given values together as bytes


def encode(fmt, nodata, values):
    chunks = [pack(fmt, nodata, v) for v in values]
    return "".encode("ascii").join(chunks)


###############################################################################
#


def test_arg_init():
    gdaltest.argDriver = gdal.GetDriverByName("ARG")
    if gdaltest.argDriver is None:
        pytest.skip()

    gdaltest.argJsontpl = """{
    "layer": "%(fmt)s",
    "type": "arg",
    "datatype": "%(dt)s",
    "xmin": %(xmin)f,
    "ymin": %(ymin)f,
    "xmax": %(xmax)f,
    "ymax": %(ymax)f,
    "cellwidth": %(width)f,
    "cellheight": %(height)f,
    "rows": %(rows)d,
    "cols": %(cols)d
}"""
    gdaltest.argDefaults = {
        "xmin": 0.0,
        "ymin": 0.0,
        "xmax": 2.0,
        "ymax": 2.0,
        "width": 1.0,
        "height": 1.0,
        "rows": 2,
        "cols": 2,
    }

    # None means "no data"
    gdaltest.argTests = [
        {
            "formats": [
                ("int8", ">b", -(1 << 7)),
                ("int16", ">h", -(1 << 15)),
                ("int32", ">i", -(1 << 31)),
                ("int64", ">q", -(1 << 63)),
            ],
            "data": [None, 2, -3, -4],
        },
        {
            "formats": [
                ("uint8", ">B", (1 << 8) - 1),
                ("uint16", ">H", (1 << 16) - 1),
                ("uint32", ">I", (1 << 32) - 1),
                ("uint64", ">Q", (1 << 64) - 1),
            ],
            "data": [None, 2, 3, 4],
        },
        {
            "formats": [
                ("float32", ">f", gdaltest.NaN()),
                ("float64", ">d", gdaltest.NaN()),
            ],
            "data": [None, 1.1, -20.02, 300.003],
        },
    ]

    for d in gdaltest.argTests:
        for (name, fmt, nodata) in d["formats"]:
            arg = open("data/arg-" + name + ".arg", "wb")
            arg.write(encode(fmt, nodata, d["data"]))
            arg.close()

            meta = copy(gdaltest.argDefaults)
            meta.update(fmt="arg-" + name, dt=name)
            json = open("data/arg-" + name + ".json", "w")
            json.write(gdaltest.argJsontpl % meta)
            json.close()

    ds = gdal.Open("data/arg-" + gdaltest.argTests[0]["formats"][1][0] + ".arg")
    if ds is None:
        gdaltest.argDriver = None

    if gdaltest.argDriver is None:
        pytest.skip()


def test_arg_unsupported():
    if gdaltest.argDriver is None:
        pytest.skip()

    for d in gdaltest.argTests:
        for (name, _, _) in d["formats"]:
            ds = gdal.Open("data/arg-" + name + ".arg")
            assert ds is not None


def test_arg_getrastercount():
    if gdaltest.argDriver is None:
        pytest.skip()

    for d in gdaltest.argTests:
        for (name, _, _) in d["formats"]:
            with gdaltest.error_handler("CPLQuietErrorHandler"):
                ds = gdal.Open("data/arg-" + name + ".arg")
            if ds is None:
                continue

            assert ds.RasterCount == 1


def test_arg_getgeotransform():
    if gdaltest.argDriver is None:
        pytest.skip()

    for d in gdaltest.argTests:
        for (name, _, _) in d["formats"]:
            with gdaltest.error_handler("CPLQuietErrorHandler"):
                ds = gdal.Open("data/arg-" + name + ".arg")
            if ds is None:
                continue

            gt = ds.GetGeoTransform()

            assert (
                gt[0] == 0
                and gt[1] == 1
                and gt[2] == 0
                and gt[3] == 2
                and gt[4] == 0
                and gt[5] == -1
            )


def test_arg_blocksize():
    if gdaltest.argDriver is None:
        pytest.skip()

    tifDriver = gdal.GetDriverByName("GTiff")
    assert tifDriver is not None

    ds = gdal.Open("data/utm.tif")
    xsize = ds.RasterXSize
    ysize = ds.RasterYSize

    # create a blocked tiff, where blocks don't line up evenly
    # with the image boundary
    ds2 = tifDriver.CreateCopy(
        "data/utm-uneven-blocks.tif",
        ds,
        False,
        ["BLOCKXSIZE=25", "BLOCKYSIZE=25", "TILED=NO"],
    )

    # convert the new blocked tiff to arg
    ds = gdaltest.argDriver.CreateCopy("data/utm.arg", ds2, False)

    ds2 = None
    ds = None

    stat = os.stat("data/utm.arg")

    os.remove("data/utm-uneven-blocks.tif")
    gdal.GetDriverByName("ARG").Delete("data/utm.arg")

    assert stat.st_size == (xsize * ysize)


def test_arg_layername():
    """
    The layer name of the ARG in the .json file need not be the name of
    the .arg file. The original driver enforced this constraint, but that
    behavior was wrong. See ticket #4609
    """
    if gdaltest.argDriver is None:
        pytest.skip()

    ds = gdal.Open("data/arg-int16.arg")

    lyr = "ARG FTW"

    # set the layer name
    ds.SetMetadataItem("LAYER", lyr)

    # did the layer name stick?
    assert ds.GetMetadata()["LAYER"] == lyr

    # copy the dataset to a new ARG
    ds2 = gdaltest.argDriver.CreateCopy("data/arg-int16-2.arg", ds, False)

    ds = None
    del ds2

    # open the new dataset
    ds = gdal.Open("data/arg-int16-2.arg")

    lyr2 = ds.GetMetadata()["LAYER"]

    ds = None
    gdal.GetDriverByName("ARG").Delete("data/arg-int16-2.arg")

    # does the new dataset's layer match the layer set before copying
    assert lyr2 == lyr

    os.unlink("data/arg-int16.arg.aux.xml")


def test_arg_nodata():
    """
    Check that the NoData value for int8 images is 128, as per the
    ARG spec. See ticket #4610
    """
    if gdaltest.argDriver is None:
        pytest.skip()

    ds = gdal.Open("data/arg-int8.arg")

    assert ds.GetRasterBand(1).GetNoDataValue() == 128


def test_arg_byteorder():
    """
    Check that a roundtrip from ARG -> GTiff -> ARG has the same
    binary values. See ticket #4779

    Unfortunately, computing statistics yields different results
    when the binary data is the same. Compare them byte-by-byte.
    """
    if gdaltest.argDriver is None:
        pytest.skip()

    tifDriver = gdal.GetDriverByName("GTiff")
    assert tifDriver is not None

    for d in gdaltest.argTests:
        for (name, _, _) in d["formats"]:

            basename = "data/arg-" + name
            with gdaltest.error_handler("CPLQuietErrorHandler"):
                orig = gdal.Open(basename + ".arg")
            if orig is None:
                continue

            dest = tifDriver.CreateCopy(basename + ".tif", orig, False)
            assert dest is not None

            mirror = gdaltest.argDriver.CreateCopy(basename + "2.arg", dest, False)
            assert mirror is not None

            orig = None
            dest = None
            mirror = None

            tmp1 = open(basename + ".arg", "rb")
            tmp2 = open(basename + "2.arg", "rb")

            data1 = tmp1.read()
            data2 = tmp2.read()

            tmp1.close()
            tmp2.close()

            gdal.GetDriverByName("GTiff").Delete(basename + ".tif")
            gdal.GetDriverByName("ARG").Delete(basename + "2.arg")

            assert data1 == data2


def test_arg_destroy():
    if gdaltest.argDriver is None:
        pytest.skip()

    for d in gdaltest.argTests:
        for (name, _, _) in d["formats"]:
            os.remove("data/arg-" + name + ".arg")
            os.remove("data/arg-" + name + ".json")
