# M1-D — WaPOR v3 scientific metadata review

**Review date:** 2026-11-21  
**Scope:** FAO WaPOR v3 product registry and the CropTwist Egypt Level-2 dekadal provider.  
**Status:** deterministic metadata guards are implemented; no live FAO raster has been downloaded or independently measured in this environment.

## Verified semantics

- WaPOR product codes encode level, variable and temporal frequency. `D` is dekadal (10 days); it does not mean a daily observation.
- Level 1 is global at nominal 300 m; Level 2 is national at nominal 100 m. The Level-1 reference evapotranspiration product is approximately 30 km and must never be presented as field-scale evidence.
- For dekadal AETI, evaporation and transpiration products, the published description is an average daily value over the 10-day period. It is not the accumulated depth over the full dekad.
- Egypt Level-2 adapter currently exposes only the six registered L2 dekadal variables. It does not claim Level-3 pilot coverage or Level-1 global products as parcel-resolution measurements.
- Product scale factors are variable-specific. AETI/E/T/I use 0.1 in the published DE Africa specification; NPP and relative soil moisture use 0.001. Do not share one scale factor across all products.

## Level-2 relative soil-moisture availability gate

The DE Africa WaPOR v3 specification lists `L2-RSM-D` and a real Egyptian raster can be read. If the live catalogue does not return it, the provider must surface an unavailable product warning rather than infer or synthesize the layer.

## Conflicting L1-I-D unit metadata

The current Digital Earth Africa WaPOR specification lists `L1-I-D` as dekadal but labels its unit `mm/year`. The FAO Google Earth Engine collection description says `L1-I-D` is a dekadal average daily interception value in `mm/day`. These statements conflict.

CropTwist therefore keeps `L1-I-D` discoverable but sets its canonical unit to unresolved (`None`). The WaPOR raster reader withholds scaled physical values whenever API/GeoTIFF metadata is malformed or disagrees with the versioned product registry. Raw raster statistics remain available for diagnosis. No unit conversion is guessed.

## Runtime safeguards

- Catalogue pagination is HTTPS, same-host, path-bounded, loop-detected and capped.
- Raster URLs are restricted to the known FAO storage host and HTTPS default port.
- Only tiled rasters are eligible for field-window reads; unbounded whole-scene reads are refused.
- API and GeoTIFF scale/unit/offset sources are all checked. A valid first source cannot hide a conflicting second source.
- Physical values are withheld on metadata conflict; provider output does not substitute a plausible-looking zero or a fabricated measurement.
- Time windows are represented as complete dekads. If a requested range intersects only part of a dekad, the full dekadal observation is returned with an explicit warning.

## Remaining verification

1. Run the WaPOR unit/contract tests on the exact PR head.
2. Perform an authorized live FAO catalogue + raster smoke test with a known Egyptian field geometry.
3. Compare selected pixels and period metadata against the FAO/DE Africa reference output before marking the provider scientifically verified.
4. Keep Level-1 RET clearly labeled as coarse reference ET if it is ever exposed; it is not a field-scale input.

## References

- Digital Earth Africa, WaPOR v3 specifications (modified 19 March 2026): https://docs.digitalearthafrica.org/en/latest/data_specs/WaPOR_specs.html
- FAO, WaPOR v3 data access and collection identifiers: https://www.fao.org/in-action/remote-sensing-for-water-productivity/wapor-data-access/en
- Google Earth Engine, WaPOR L1 interception dekadal collection: https://developers.google.com/earth-engine/datasets/catalog/FAO_WAPOR_3_L1_I_D
- Google Earth Engine, WaPOR L1 dekadal reference evapotranspiration: https://developers.google.com/earth-engine/datasets/catalog/FAO_WAPOR_3_L1_RET_D
