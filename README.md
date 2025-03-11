This repository contains the following utilities, which may or may not be useful for some...

# boundary_subset.py

Extract NextGen Hydrofbric Elements from Shapefile Geometries. Currently only supports v2.2 hydrofabric.  Some assumptions of this tool that are important to note:

- The geometries in the given shapefile should be contained in the overal extent of the gpkg used to subset from.
- The geometries in the given shapefil must *cross* the flowpath network geometries.


positional arguments:
  gpkg                  Path to geopackage (may be a valid s3 path)

options:
  --ghost, -g           Include the downstream flowpath in the extracted elements
  --output-dir, -o      The output directory used to for saving the geospatial boundary subsets and/or plots

Shapefile Arguments:
  boundaries            Path to file containing boundaries to use
  -f FIELD, --field FIELD
                        Field to use for boundary selection and/or naming
  -i [IDS ...], --ids [IDS ...]
                        Ids to use for boundary selection
  
>[!NOTE] 
>If IDS are not provided, then this utility will iterate over all geometries in the shapefile, naming each output based on the FIELD value assoicated with that geometry.

Plotting Arguments:
  --plot, -p            Plot the extracted elements
  --plot-wide, -w       Plot the extracted elements with a wider view (the bounding box of the boundary geometry being processed)
  --save, -s            Save the plot to a file
  --interactive, -I     Use interactive plotting

>[!NOTE]
>If interactive plotting, the resulting subset will be displayed for each geometry being processed.  Once the plot is closed, then the utility will proceed to the next.

When saving plots, the selected plots will be saved to png files with the FIELD value prepended to the filename.

When complete, a geopackage containing the subset of NextGen Hydrofabric elements for each input boundary will be generated and saved, with the FIELD value of each boundary prepended to the filename.

>[!IMPORTANT] 
>When used with Lynker Spatial hydrofabric, either locally or via S3, the resulting subsets are governed by the following data liscence:

```
The Cloud Native Water Resource Modeling Hydrofabric dataset is made available under the Open Database License (ODbL).


You are free to use, copy, distribute, transmit and adapt our data, as long as you credit Lynker and its contributors.


Johnson, J. M. (2022). National Hydrologic Geospatial Fabric (hydrofabric) for the Next Generation (NextGen) Hydrologic Modeling Framework,
HydroShare http://www.hydroshare.org/resource/129787b468aa4d55ace7b124ed27dbde


Any rights in individual contents of the dataset are licensed under the Database Contents License.
```
