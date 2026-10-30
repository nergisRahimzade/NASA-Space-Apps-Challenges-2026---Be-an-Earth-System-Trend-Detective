# MOD11C3.061 variable glossary

**ESD-D06-DAT** | Sample: `MOD11C3.A2024122.061.2024162162404.hdf`

This file covers May 1-31, 2024. It opens directly with
`xr.open_dataset(..., engine="netcdf4", mask_and_scale=False, decode_times=False)`
in the project environment. Packed values, quality flags and bitmaps remain intact.

## Dimensions

| Source dimension | Size | Meaning |
| --- | --- | --- |
| `YDim:MODIS_MONTHLY_0.05DEG_CMG_LST` | 3,600 | Rows from north to south; latitude centers 89.975 to -89.975 degrees. |
| `XDim:MODIS_MONTHLY_0.05DEG_CMG_LST` | 7,200 | Columns from west to east; longitude centers -179.975 to 179.975 degrees. |

Every variable uses these two dimensions. The global grid spacing is 0.05 degrees
(3 arcminutes). The file has no time or band dimension and no latitude/longitude
coordinate variables. Its month comes from `CoreMetadata.0`; plotting coordinates
are derived from the geographic grid in `StructMetadata.0`.

## Variables

Names and attributes were checked against the actual file and the
[NASA monthly product specification](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD11C3).
Ranges below refer to stored integers; exclude numeric fill values before decoding.

| Variable | Meaning | Type; valid range; fill | Physical value or interpretation |
| --- | --- | --- | --- |
| `LST_Day_CMG` | Monthly daytime land surface temperature | uint16; 7500-65535; 0 | raw x 0.02 K |
| `QC_Day` | Daytime LST and emissivity quality | uint8; 0-255; no numeric fill | Monthly QC bit fields below |
| `Day_view_time` | Average daytime observation time | uint8; 0-120; 255 | raw x 0.2 hours UTC |
| `Day_view_angl` | Average daytime viewing zenith angle | uint8; 0-130; 255 | raw - 65 degrees |
| `Clear_sky_days` | Dates with clear sky and valid daytime LST | uint32; 0-4294967295; no numeric fill | Calendar-day bitmap |
| `LST_Night_CMG` | Monthly nighttime land surface temperature | uint16; 7500-65535; 0 | raw x 0.02 K |
| `QC_Night` | Nighttime LST and emissivity quality | uint8; 0-255; no numeric fill | Monthly QC bit fields below |
| `Night_view_time` | Average nighttime observation time | uint8; 0-120; 255 | raw x 0.2 hours UTC |
| `Night_view_angl` | Average nighttime viewing zenith angle | uint8; 0-130; 255 | raw - 65 degrees |
| `Clear_sky_nights` | Dates with clear sky and valid nighttime LST | uint32; 0-4294967295; no numeric fill | Calendar-day bitmap |
| `Emis_20` | MODIS band 20 emissivity | uint8; 1-255; 0 | raw x 0.002 + 0.49; dimensionless |
| `Emis_22` | MODIS band 22 emissivity | uint8; 1-255; 0 | raw x 0.002 + 0.49; dimensionless |
| `Emis_23` | MODIS band 23 emissivity | uint8; 1-255; 0 | raw x 0.002 + 0.49; dimensionless |
| `Emis_29` | MODIS band 29 emissivity | uint8; 1-255; 0 | raw x 0.002 + 0.49; dimensionless |
| `Emis_31` | MODIS band 31 emissivity | uint8; 1-255; 0 | raw x 0.002 + 0.49; dimensionless |
| `Emis_32` | MODIS band 32 emissivity | uint8; 1-255; 0 | raw x 0.002 + 0.49; dimensionless |
| `Percent_land_in_grid` | Land percentage within a grid cell | uint8; 1-100; 0 | Percent; 0 is fill, not a valid 0% measurement |

For `Clear_sky_*`, bit 0 represents the first day/night of the month, bit 1 the
second, through bit 30 for the 31st. A set bit identifies a valid clear-sky
observation; the integer itself is not a count.

| QC bits | Meaning in this monthly product |
| --- | --- |
| 0-1 | Mandatory LST quality |
| 2 | Level-1B input quality |
| 3 | Terra/Aqua combined-use flag |
| 4-5 | Monthly emissivity consistency |
| 6-7 | Average LST error class |

QC and bitmap fill declarations are `NA` text with NUL padding, not numeric 0.
Use the monthly QC specification rather than the daily-product layout.

## Attributes and inspection outputs

Variable attributes provide descriptions, storage types, valid ranges, fill values
and scaling. The six global attributes describe the HDF-EOS version, grid structure,
product DOI and DOI authority, product/date metadata, and archive metadata.
The [inventory](evidence/day6/sample_inventory.json) records every variable and
all source attributes; NUL padding is escaped in JSON.

The [map](evidence/day6/phoenix_nighttime_lst_2024-05.png) shows the fixed Phoenix
window: 12 x 16 cells. Only its display values are scaled to Kelvin and masked for
fill/range. No QC filter is applied, and no cleaned dataset is saved.
