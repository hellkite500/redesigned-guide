#!/usr/bin/env python

"""
@author Nels Frazier

@date Febuary 28, 2025
@version 0.1

Copyright (C) 2025 Nels Frazier

Utility for extracting hydrofabric elements from a shapefile geometry.
This script will extract the largest complete network of hydrofabric 
elements which intersects/crosses boundaries provided in the shapefile.
The extracted elements will be written to a new geopackage file.

Currently supports NextGen hydrofabric v2.2

"""
# TODO reuse global layers for multiple boundaries when getting sub layers
# TODO save both wide and exact plots

import argparse
from collections import deque
from collections.abc import Iterable
import geopandas as gpd
from matplotlib import pyplot as plt
import pandas as pd
from pathlib import Path
import s3fs
from typing import Optional, Mapping

def intersects_flowpaths(flowpaths: gpd.GeoDataFrame, boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Extracts the flowpaths that intersect with the given boundaries.
    """
    return gpd.sjoin(flowpaths, boundaries, how='inner', predicate='crosses')
    #return flowpaths[ flowpaths.crosses(boundaries, align=False)]

def trace_up(id: str, flowpaths: gpd.GeoDataFrame, network: pd.DataFrame) -> Iterable[str]:
    """Trace the network upstream from the given id

    Args:
        id (str): flowpath id to trace upstream
        flowpaths (gpd.GeoDataFrame): flowpath hydrofabric table
        network (pd.DataFrame): network hydrofabric table

    Returns:
        Iterable[str]: list of flowpath ids that are upstream of the given id
    """
    #make the queries in the trace loop a little faster by removing duplicates
    network = network.drop_duplicates(subset=['id', 'toid'], keep='first')
    wbs = [id]
    todo = deque( network[ network['toid'] == id ]['id'].tolist() )
    # to_idx = network.set_index('toid')
    while len(todo) > 0:
        nex_up = todo.pop()
        #wb = to_idx.loc[ [nex_up] ]['id'].unique()
        #wb = network[ network['toid'] == nex_up ]['id'].unique()
        #wb = network.query('toid == @nex_up')['id'].unique()
        # It is marginally faster to do this query on the flowpaths since
        # it is already clipped and a much smaller set to search
        wb = flowpaths.query('toid == @nex_up')['id'].unique()
        wbs.extend( wb )
        # Must query this from the network for nexus connectivity
        #next = to_idx[ to_idx.index.isin(wb) ]['id'].unique()
        #next = network[ network['toid'].isin(wb) ]['id'].tolist()
        next = network.query('toid in @wb')['id'].unique()
        todo.extend( next )
    return wbs

def plot_sub(boundary: gpd.GeoDataFrame, sub_flowpaths: gpd.GeoDataFrame, sub_divides: gpd.GeoDataFrame, divides: Optional[gpd.GeoDataFrame]=None, flowpaths: Optional[gpd.GeoDataFrame]=None, crosses: Optional[gpd.GeoDataFrame]=None, save: Optional[str]=None, interactive: bool=False) -> None:
    """Plot the subnetwork geometries

    Args:
        boundary (gpd.GeoDataFrame): Boundary used to trace the subnetwork within
        sub_flowpaths (gpd.GeoDataFrame): Flowpaths of the subnetwork
        sub_divides (gpd.GeoDataFrame): Divides of the subnetwork
        divides (Optional[gpd.GeoDataFrame], optional):  Additional divides to plot. Defaults to None.
        flowpaths (Optional[gpd.GeoDataframe], optional):  Additional flowpaths to plot. Defaults to None.
        crosses (Optional[gpd.GeoDataFrame], optional): The identified flowpaths which cross the boundary (will be labled). Defaults to None.
        save (Optional[str], optional): Save the plot with the string prefix. Defaults to None.
        interactive (bool, optional): Use interactive plotting. Defaults to False.
    """
    ax = boundary.plot( color='red', alpha=0.5)
    if flowpaths is not None:
        ax = flowpaths.plot(ax=ax, color='blue', alpha=0.5)
    if crosses is not None:
        ax = crosses.plot(ax=ax, label='id', color='green')
        crosses.apply(lambda x: ax.annotate(text=x.name, xy=x.geometry.centroid.coords[0], ha='center'), axis=1)
    if divides is not None:
        ax = divides.plot(ax=ax, facecolor='none', edgecolor='black')
    ax = sub_flowpaths.plot(ax=ax, color='blue')
    ax = sub_divides.plot(ax=ax, facecolor='none', edgecolor='red')
    
    if save is not None:
        plt.savefig(f"{save}_hydrofabric_subset.png")
    if interactive:
        plt.show()

def find_mainstem(boundary: gpd.GeoDataFrame, flowpaths: gpd.GeoDataFrame, network: pd.DataFrame) -> tuple[Iterable[str], str, gpd.GeoDataFrame]:
    """Find flowpaths which cross the given boundary, then trace each flowpath upstream to find the mainstem (the largest resulting network)

    Args:
        boundary (gpd.GeoDataFrame): polygon boundary which intersects at least one flowpath in the hydrofabric
        flowpaths (gpd.GeoDataFrame): hydrofabric flowpaths
        network (pd.DataFrame): hydrofabric network

    Returns:
        tuple[Iterable[str], str, gpd.GeoDataFrame]: The list of flowpath ids which make up the mainstem, the terminal nexus of the mainstem, and the flowpaths which cross the boundary
    """
    xmin, ymin, xmax, ymax = boundary.total_bounds

    flowpaths = flowpaths.cx[xmin:xmax, ymin:ymax]
    print("Finding flowpaths...")
    which = intersects_flowpaths(flowpaths, boundary)

    print("Finding mainstem...")
    mainstem = []
    for id in which.index:
        index = trace_up(id, flowpaths.reset_index(), network[['id', 'toid']])
        if len(index) > len(mainstem):
            mainstem = index

    terminal_path = flowpaths.loc[mainstem[0]]
    terminal_nexus = terminal_path['toid']
    return mainstem, terminal_nexus, which

def _get_layers_from_nex(gpkg: Path, nexus: pd.Series) -> Mapping[str, gpd.GeoDataFrame]:
    """Get hydrofabric layers which are indexed by nexus ids

    Args:
        gpkg (Path): hydrofabric geopackage
        nexus (pd.Series): nexus ids of interest

    Returns:
        Mapping[str, gpd.GeoDataFrame]: Mapping of layer names to layers extracted by nexus ids
    """
    nex = gpd.read_file(gpkg, layer='nexus', use_arrow=True)
    nex = nex.query('id in @nexus')
    pois = gpd.read_file(gpkg, layer='pois', use_arrow=True)
    pois = pois.query('nex_id in @nexus')
    hydro = gpd.read_file(gpkg, layer='hydrolocations', use_arrow=True)
    hydro = hydro.query('nex_id in @nexus')

    return {"nexus": nex, "pois": pois, "hydrolocations": hydro}

def _get_layers_from_flowpath(gpkg: Path, flowpaths: pd.Series)-> Mapping[str, gpd.GeoDataFrame]:
    """Get hydrofabric layers which are indexed by flowpath ids

    Args:
        gpkg (Path): hydrofabric geopackage
        flowpaths (pd.Series): flowpath ids of interest

    Returns:
        Mapping[str, gpd.GeoDataFrame]: Mapping of layer names to layers extracted by flowpath ids
    """
    attrs = gpd.read_file(gpkg, layer='flowpath-attributes', use_arrow=True)
    attrs = attrs.query('id in @flowpaths')
    attrs_ml = gpd.read_file(gpkg, layer='flowpath-attributes-ml', use_arrow=True)
    attrs_ml = attrs_ml.query('id in @flowpaths')

    return {"flowpath-attributes": attrs, "flowpath-attributes-ml": attrs_ml}

def _get_layers_from_poi(gpkg: Path, pois: pd.Series)->Mapping[str, gpd.GeoDataFrame]:
    """Get hydrofabric layers which are indexed by poi ids

    Args:
        gpkg (Path): hydrofabric geopackage
        pois (pd.Series): poi ids of interest

    Returns:
        Mapping[str, gpd.GeoDataFrame]: Mapping of layer names to layers extracted by poi ids
    """

    # NJF TODO verify this poi relationship exists for all lakes...
    lakes = gpd.read_file(gpkg, layer='lakes', use_arrow=True)
    lakes = lakes.query('poi_id in @pois')

    return {"lakes": lakes}

def get_sub_layers(gpkg: Path, mainstem: Iterable[str], ghost:Optional[str]=None)->Mapping[str, gpd.GeoDataFrame]:
    """Extract the hydrofabric layers for the given mainstem

    Args:
        gpkg (Path): hydrofabric geopackage
        mainstem (Iterable[str]): list of flowpath ids which make up the mainstem
        ghost (Optional[str]): Add the downstream flowpath from this id (and terminal nexus) to the flowpath table. Defaults to None.

    Returns:
        Mapping[str, gpd.GeoDataFrame]: Mapping of layer names to layer subset tables
    """
    flowpaths = gpd.read_file(gpkg, layer='flowpaths', use_arrow=True).set_index('id')
    divides = gpd.read_file(gpkg, layer='divides', use_arrow=True)
    divide_attrs = gpd.read_file(gpkg, layer='divide-attributes', use_arrow=True)
    network = gpd.read_file(gpkg, layer='network', use_arrow=True)
    sub_flowpaths = flowpaths.loc[ mainstem ]
    sub_divides = divides[ divides['divide_id'].isin(sub_flowpaths['divide_id']) ]

    divide_attrs = divide_attrs[ divide_attrs['divide_id'].isin(sub_divides['divide_id']) ]

    if ghost is not None:
        ghost_path = network[ network['id'] == ghost ]['toid'].to_list()
        ghost_nex = "tnx-0"
        sub_flowpaths = flowpaths.loc[ ghost_path+mainstem ]

    l1 = _get_layers_from_flowpath(gpkg, sub_flowpaths.index)
    l2 = _get_layers_from_nex(gpkg, sub_flowpaths['toid'])
    # NJF I think this is sufficient?  flowpaths shouldn't have POI's, only nexus
    l3 = _get_layers_from_poi(gpkg, sub_flowpaths['toid'])

    network.set_index('id', inplace=True)
    sub_network = pd.concat( ( network.loc[ sub_flowpaths.index], network.loc[ sub_flowpaths['toid'].values ] ) )
    if ghost is not None:
        sub_network.loc[ghost_path, 'toid'] = ghost_nex

    return {"flowpaths": sub_flowpaths.reset_index(), "divides": sub_divides, "divide-attributes": divide_attrs, "network": sub_network.reset_index(), **l1, **l2, **l3}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract NextGen Hydrofbric Elements from Shapefile Geometries. Currently only support v2.2 hydrofabric')
    shp_group = parser.add_argument_group('Shapefile Arguments')
    shp_group.add_argument('boundaries', type=Path, help='Path to file containing boundaries to use')
    shp_group.add_argument('-f', '--field', type=str, help='Field to use for boundary selection and/or naming', required=True)
    shp_group.add_argument('-i', '--ids', type=str, nargs='*', help='Ids to use for boundary selection')
    parser.add_argument('gpkg', type=Path, help='Path to geopackage (may be a valid s3 path)')
    plt_group = parser.add_argument_group('Plotting Arguments') 
    plt_group.add_argument('--plot', '-p', action='store_true', help='Plot the extracted elements')
    plt_group.add_argument('--plot-wide', '-w', action='store_true', help='Plot the extracted elements with a wider view (the bounding box of the boundary geometry being processed)')
    plt_group.add_argument('--save', '-s', action='store_true', help='Save the plot to a file')
    plt_group.add_argument('--interactive', '-I', action='store_true', help='Use interactive plotting')
    parser.add_argument('--ghost', '-g', action='store_true', help='Include the downstream flowpath in the extracted elements')
    parser.add_argument('--output-dir', '-o', type=str, help='The output directory used to for saving the geospatial boundary subsets and/or plots')
    args = parser.parse_args()

    shp = args.boundaries
    gpkg = args.gpkg

    if str(gpkg).startswith('s3:'):
        _s3 = s3fs.S3FileSystem(profile='default')
        _to_open = _s3.open(str(gpkg).replace("s3:/", "s3://"))
    else:
        _to_open = gpkg
        
    if args.output_dir is not None:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(exist_ok=True)
    else:
        output_dir = Path("./")

    # use_arrow here makes these reads 2-3x faster, especially for
    # reading the network table
    network = gpd.read_file(_to_open, layer='network', use_arrow=True)
    flowpaths = gpd.read_file(_to_open, layer='flowpaths', use_arrow=True).set_index('id')
    if args.plot_wide:
        divides = gpd.read_file(_to_open, layer='divides', use_arrow=True)
    
    boundaries = gpd.read_file(shp)

    # reproject to hydrofabric crs
    boundaries.to_crs(flowpaths.crs, inplace=True)

    boundaries[args.field] = boundaries[args.field].astype(str)
    boundaries.set_index(args.field, inplace=True)
    if args.ids:
        boundaries = boundaries.loc[args.ids]

    for name, boundary in boundaries.iterrows():
        print(f"Extracting hydrofabric for {name}")
        boundary = gpd.GeoDataFrame([], crs=boundaries.crs, geometry=[boundary.geometry])
        xmin, ymin, xmax, ymax = boundary.total_bounds
    
        fp_clipped = flowpaths.cx[xmin:xmax, ymin:ymax]
        # Find mainstem ids
        mainstem, terminal_nexus, which = find_mainstem(boundary, fp_clipped, network)
        ghost = None
        if args.ghost:
            ghost = terminal_nexus
        # Subset all layers
        all = get_sub_layers(_to_open, mainstem, ghost=terminal_nexus)
        
        # Compute the percent coverage
        total_divide_area = all['divides']['geometry'].area.sum()
        # SHOULD only be a single area, so take the first...
        boundary_area = boundary['geometry'].area.values[0]
        print(f"Percent of boundary area covered by hydrofabric subset: {(total_divide_area/boundary_area)*100:.2f}%")

        # If asked, plot the extracted flowpaths and divides
        if args.plot or args.plot_wide:
            print("Plotting...")
            save = None
            if not args.plot_wide:
                div_clipped = None
                fp_clipped = None
            else:
                div_clipped = divides.cx[xmin:xmax, ymin:ymax]
            if args.save:
                save = name
            plot_sub(boundary, all['flowpaths'], all['divides'], div_clipped, fp_clipped, crosses=which, save=save, interactive=args.interactive)

        print(f"Writing subset to {name}_{terminal_nexus}.gpkg")
        print()
        # Write to a new geopackage
        for table, layer in all.items():
            gpd.GeoDataFrame(layer).to_file(output_dir / f"{name}_{terminal_nexus}.gpkg", layer=table, driver='GPKG')
