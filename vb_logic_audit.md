# Visual Basic to Vectorized Python Code Translation Harness & Agronomic Audit

This document establishes the official computational translation harness and biophysical audit ledger between the legacy Soltani-Sinclair Visual Basic crop model (`iCrop_ALLCrops Code_20240626_JH.vb`) and the high-performance, object-oriented, vectorized Python simulation engine (`core/model_engine.py`) inside the **iCrop 2** platform.

---

## 1. Biophysical Architecture & Translation Mapping

The legacy model implements a simple daily crop growth model for wheat, barley, maize, sorghum, potato, and grain legumes. The core mathematical routines are structured as separate subroutines (`GoSub`) representing daily physical modules:

| Visual Basic Subroutine | Biophysical Process Model | Vectorized Python Implementation Route |
| :--- | :--- | :--- |
| `GoSub Weather` | Atmospheric reanalysis inputs | Chronological pandas dataframe parsing |
| `GoSub PhenologyBD` | Biological GDD development | Cardinal thermal stress beta/dent curves |
| `GoSub CropLAI` / `CropLAIN` | Canopy leaf expansion | Carbon-limited area expansion loops |
| `GoSub DMProduction` | Biomass accumulation (RUE) | Light interception ($FINT$) & radiation scaling |
| `GoSub DMDistribution` | Carbohydrate partitioning | Daily harvest index ($HI$) partitioning ceiling |
| `GoSub SoilWater` | Hydrology tipping-bucket | Multi-layer 5-zone volumetric drainage matrix |
| `GoSub SoilN` | Nitrogen solute balance | Volumetric leaching dilution fraction |

---

## 2. Drop-Text Logic Translation Harness

To import a legacy equation or logic function from the Visual Basic source code:
1. **Locate the target Visual Basic code snippet** in `iCrop_ALLCrops Code_20240626_JH.vb`.
2. **Drop the raw code block** into the translation context.
3. **Map the arrays and variables** to vectorized NumPy equations according to the following conventions:

### Array and State Variable Mapping Conventions

| Legacy VB Variable | Physical Meaning | Clean Python Variable / Array |
| :--- | :--- | :--- |
| `DLYER(L)` | Soil layer thickness (mm) | `dlyer = np.array(self.soil_params["DLYER"])` |
| `WL(L)` | Current water depth in layer $L$ (mm) | `wl` (numpy 1D array of length $N_{layer}$) |
| `WLAD(L)` | Air-dry limit water depth (mm) | `wlad = adry * dlyer` |
| `WLLL(L)` | Lower limit water depth (mm) | `wlll = cll * dlyer` |
| `WLUL(L)` | Upper limit water depth (mm) | `wlul = dul * dlyer` |
| `WLST(L)` | Saturation water depth (mm) | `wst = sat * dlyer` |
| `FTSW(L)` | Fraction of transpirable soil water | `fts_layer = (wl - wlll) / (wlul - wlll)` (clamped `[0, 1]`) |
| `RT(L)` | Root activity weighting factor | `rt` (numpy 1D array of active root weights) |

---

## 3. Mathematical Reference Formula Audits

### A. Cardinal Temperature Development Stress
#### Legacy Visual Basic Code (Beta Function for C3 crops like Wheat/Barley)
```vb
part1 = (TCD - TMP) / (TCD - TP1D)
part2 = (TMP - TBD) / (TP1D - TBD)
pow = (TP1D - TBD) / (TCD - TP1D)
tempfun = (part1 * part2 ^ pow)
```
#### Vectorized Python Implementation
```python
def calculate_stress_factor(self, tmp: float, tb: float, tp1: float, tp2: float, tcd: float) -> float:
    if not (tb < tmp < tcd):
        return 0.0
    if tp1 <= tmp <= tp2:
        return 1.0
    # Beta curve scaling for off-optimal conditions
    part1 = (tcd - tmp) / (tcd - tp1)
    part2 = (tmp - tb) / (tp1 - tb)
    power = (tp1 - tb) / (tcd - tp1)
    return float(part1 * (part2 ** power))
```

### B. Daily Soil Water Balance Tipping-Bucket (Volumetric Redistribution)
#### Legacy Visual Basic Code
```vb
For L = 1 To NLYER - 1
    If WL(L) > WLUL(L) Then
       drain = DRAINF(L) * (WL(L) - WLUL(L))
       WL(L) = WL(L) - drain
       WL(L + 1) = WL(L + 1) + drain
    End If
Next L
```
#### Vectorized Python Implementation
```python
# Programmatically execute downward volumetric gravity cascading (tipping-bucket)
excess = np.maximum(0.0, wl - wlul)
drainage = drainf * excess
wl[:-1] += drainage[1:] # shift up: layer L+1 gets drainage from layer L
wl -= drainage
```

### C. Nitrogen Solute Transport Leaching
#### Legacy Visual Basic Code
```vb
leach = (drain / WL(L)) * SNAVL
```
#### Upgraded Dilution Equation (Vectorized & Mass-Conserving)
```python
leaching_fraction = np.maximum(0.0, np.minimum(0.75, daily_drainage / np.maximum(0.001, wl[ldrain])))
n_leached_daily = np.minimum(SNAVL * leaching_fraction * leaching_efficiency, SNAVL)
```

---

## 4. Active Translation Harness Checklist
- [x] Create isolated system utility database seeding from multi-crop parameters spreadsheet.
- [x] Establish biophysical variable mappings to numpy vectorized arrays.
- [ ] Drop Visual Basic modules and expand support to grain legumes (`Soybean`, `Chickpea`, `FabaBean`, `FieldPea`).
