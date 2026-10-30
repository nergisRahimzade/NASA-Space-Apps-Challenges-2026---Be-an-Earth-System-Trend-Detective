# Combined monthly data

**ESD-D07-DAT** | MOD11C3.061 | January 2003-December 2024

## Combined dataset

- 264 monthly files opened with `xr.open_mfdataset(..., combine="by_coords")`.
- Dimensions: `time=264`, original north-to-south `YDim=3600`, west-to-east
  `XDim=7200`; all 17 variables retained.
- Each file's product, version, month and geographic grid were checked. A
  month-start `time` coordinate was added from its actual date metadata.
- The combined calendar has no missing or duplicate months. Raw nighttime LST
  was read at one fixed cell for all 264 months to confirm source access.
- Variable types, shapes and attributes are consistent across every file.
  File-specific `CoreMetadata.0` and `ArchiveMetadata.0` differ and are dropped;
  the combined dataset carries the full study-period dates instead.

The dataset opens lazily from the existing HDF files. It retains global packed
values and quality flags; no combined or cleaned data file is written.
The [check record](evidence/day7/combined_check.json) contains the calendar,
dimensions, variable metadata and read check.

## Units and fill values

The values remain packed integers. Apply these definitions after excluding fill
and out-of-range values; full ranges are in the [variable glossary](data_glossary.md).

| Fields | Physical units or meaning | Fill |
| --- | --- | --- |
| `LST_Day_CMG`, `LST_Night_CMG` | raw x 0.02 K | 0 |
| `Day_view_time`, `Night_view_time` | raw x 0.2 hours UTC | 255 |
| `Day_view_angl`, `Night_view_angl` | raw - 65 degrees | 255 |
| `Emis_20/22/23/29/31/32` | raw x 0.002 + 0.49; dimensionless | 0 |
| `Percent_land_in_grid` | Percent; valid stored range 1-100 | 0 |
| `QC_Day`, `QC_Night` | Monthly quality bit fields | NA text; no numeric fill |
| `Clear_sky_days`, `Clear_sky_nights` | Calendar-day bitmaps | NA text; no numeric fill |

## Problems to fix before analysis

- Decode numeric fill/range values to NaN, convert LST to Celsius, rename
  spatial dimensions and select Phoenix during Day 8 cleaning.
- Resolve the monthly production QC and valid-coverage policy. The
  [Day 3 sample finding](data_notes.md#sample-check) remains relevant; a complete
  monthly calendar does not establish valid observations in every cell.
