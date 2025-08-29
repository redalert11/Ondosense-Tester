# OndoSense RS‑485 Quick Reference & Recommended Settings

**Applies to**: OndoSense sensors speaking the “OS1 Application Note” RS‑485 protocol (March 2024).  
**Focus**: Practical, field‑tested starting points for distance measurement, spectrum/IQ, and quick tuning.

> ⚠️ Always verify on your exact variant. Some ranges and features (e.g., **High‑Precision Distance**) are model‑dependent.

---

## Quick Start

1. **Wire**: A/B (RS‑485), V+ **24 V**, V‑ GND. Tie grounds between host and sensor.
2. **PC serial**: 8‑N‑1. Default **baud 19 200** (changeable).
3. **Poll**: Send `0x03` for one measurement. The returned data depends on **Result Data Selector (0x41)**.
4. **Save**: Use `0x0F` to persist *most* parameters **except** baud rate and result selector.
5. **Debug**: Read a parameter with `0x01 <PID>`, write with `0x02 <PID> <int32_be>`.

---

## Recommended Baselines (by use‑case)

| Use‑case | Selector (0x41) | PC Baud | Meas. Rate (0x43) | Profile (0x48) | Notes |
|---|---|---:|---:|---|---|
| **Simple distance** | `16` (Distance) | 115 200 | 10 Hz | 2 (LR Fast) | Stable & low‑latency. |
| **Distance + health** | `16 + 128` (Distance + Count) | 115 200 | 10–20 Hz | 2 or 5 | Count helps spot missed frames. |
| **Peak/distance list** | `64` (Distance List) | 230 400 | 5–10 Hz | 3 (Close) | For multi‑target scenes. |
| **Spectrum view** | `2` (Spectrum) | 230 400+ | 2–10 Hz | 3 or 16 | Heavier payload → faster baud. |
| **IQ analysis** | `1` (IQ) | 230 400+ | 1–5 Hz | 3 or 16 | Use when doing custom DSP. |
| **High‑precision mode** | `512` (+ optional 16) | 115 200 | 5–10 Hz | Variant‑dependent | Tune HP threshold/timeout as needed. |

> Tip: When streaming **Spectrum** or **IQ**, bump baud to **230 400 or 460 800** and keep rates ≤10 Hz to avoid PC‑side overruns.

---

## Parameter Reference & Suggested Starting Points

### 1) Measurement Selection & Rate
| Name | PID | Range / Default | What it does | Recommended |
|---|---|---|---|---|
| **Result Data Selector** | `0x41` | Bitmask (IQ=1, Spectrum=2, PeakList=4, Peak=8, Distance=16, DistList=64, MeasCount=128, Temp=256, High‑Precision=512). Default: **16** (Distance). | Chooses what the sensor serializes after a `0x03` command (you may combine bits). | Start with 16 for distance. Add 128 for health, 2 for spectrum, 1 for IQ. Read the status byte before **each** dataset if combining. |
| **Measurement rate** | `0x43` | `1..max` (variant‑dependent) / Default: *max* | Internal acquisition cadence. | 10 Hz is a good baseline for UI; increase once comms are stable. |

**Selector bitmask examples**  
- Distance only: `16`  
- Distance + Count: `16 + 128 = 144`  
- Spectrum + Distance: `2 + 16 = 18`

### 2) Range, Averaging, Profiles
| Name | PID | Range / Default | What it does | Recommended |
|---|---|---|---|---|
| **Minimal distance** | `0x44` | Variant‑specific / Default: model‑specific | Rejects targets closer than this. | Set slightly below your nearest expected target. |
| **Maximal distance** | `0x45` | Variant‑specific / Default: model‑specific | Rejects targets beyond this. | Set just above your farthest expected target for faster, cleaner results. |
| **Integrations (raw)** | `0x46` | `1..10000` / **1** | Accumulate multiple ramps (IQ path). | Low SNR/static scenes: 5–20. Fast motion: 1–2. |
| **Integrations (spectrum)** | `0x47` | `1..10000` / **1** | Averaging for spectrum. | 4–16 for a smooth spectrum at moderate rates. |
| **Radar profile** | `0x48` | {**2** LR‑Fast, **3** Close (≤5 m), **5** LR‑Slow, **16** Max Accuracy (≤6 m)} / **2** | Sets ramp schema and filtering tuned for the use‑case. | Close‑range indoor walls: **3** or **16**. Long hallway / outdoors: **2** (moving) or **5** (static). |

> Note: Available profiles and maximum rates are variant‑dependent. Distances outside the calibrated range may reduce accuracy.

### 3) High‑Precision Mode (if supported)
| Name | PID | Range / Default | What it does | Recommended |
|---|---|---|---|---|
| **HP distance threshold** | `0x83` | `1..max` / **25 (1/(2λ))** | Gate for HP lock‑on. | Start at default; reduce slightly if HP fails to lock in stable setups. |
| **HP timeout** | `0x84` | `0..max` / **5000 ms** | Time until HP unlocks. | Keep 3–5 s for handheld; shorten to 1–2 s if you move quickly. |
| **Restart HP (cmd)** | `0x19` | — | Manual reset of HP tracking. | Bind to a UI button. |

### 4) Signal Chain & Detection
| Name | PID | Range / Default | What it does | Recommended |
|---|---|---|---|---|
| **Preamp gain Q/I** | `0x70/0x71` | `0..255` / **127** | Analog gain. | Leave defaults; use **Autoset amplifier (0x07)** once per setup. |
| **ADC gain Q/I** | `0x72/0x73` | `0..255` / **127** | Digital gain. | Leave defaults unless you know you’re saturating. |
| **RX delay** | `0x90` | `0..100000 µs` / **5000 µs** | Receiver timing alignment. | Default is fine; adjust only for unusual installations. |
| **Threshold sensitivity** | `0x91` | `0..max` / **10** | Detection sensitivity. | If you miss weak targets, increase slightly. |
| **Threshold offset** | `0x82` | `0..max` / **0** | Shifts detection threshold. | Keep at 0 unless you’re filtering noise. |
| **Distance offset** | `0xED` | `[-minDist .. maxDist]` / **0 mm** | Adds a fixed offset to measured distance. | Calibrate with a known reference target; store offset. |
| **EMA time** | `0x96` | `0..max ms` / **0** | Output smoothing. | For UI only: 100–300 ms for steady plot; leave 0 for control loops. |
| **Outlier max time** | `0x97` | `0..max ms` / **0** | Rejects blips older than X ms. | 100–300 ms to suppress spikes. |
| **Outlier max distance** | `0x98` | `0..max` / **0** | Rejects big jumps in distance. | 20–50 mm for wall mapping. |
| **Outlier max speed** | `0x99` | `0..max µm/s` / **0** | Rejects targets exceeding speed. | Set per application; leave 0 if unsure. |
| **Peak sorting** | `0x92` | 0..5 / **1 (Amplitude)** | Order for peak list. | 0 (Distance) for nearest‑object logic; 1 for strongest‑return logic. |
| **Peak index** | `0x93` | 0..4 / **0** | Pick which peak after sorting. | Usually 0. |

### 5) Communications & Outputs
| Name | PID | Range / Default | What it does | Recommended |
|---|---|---|---|---|
| **Baud rate** | `0x49` | `9600..921600` / **19200** | Serial line speed. | 115 200 for general use; **230 400+** for Spectrum/IQ. Remember to reopen port after writing. |
| **Save params (cmd)** | `0x0F` | — | Persists all **except** selector & baud. | Save before power cycle. |
| **Autoset amplifier (cmd)** | `0x07` | — | Automatic gain provisioning. | Run after mounting or target change. |
| **Background cal/remove (cmd)** | `0x0D` / `0x0E` | — | Subtracts static background. | Cal when scene is static; remove when moving. |
| **Switching outputs enable** | `0xC0..0xC2` | 0/1 / **1** | Digital outputs. | If unused, set selection to *Input* (`0xDF..0xE1 = 1`) or disable to avoid surprises. |
| **Current loop** | `0xB0..0xB2` | model‑specific | 4–20 mA scaling and error behavior. | Configure only if you wire 4–20 mA; otherwise ignore. |

---

## Command Cheatsheet

- **Read parameter**: `01 <pid>` → `01 <int32_be>`  
- **Write parameter**: `02 <pid> <int32_be>` → `01`  
- **Measurement**: `03` → status + result(s) according to selector  
- **Read min/max**: `10 <pid>` / `11 <pid>` → `01 <int32_be>`  
- **Save**: `0F` (selector & baud not saved)  
- **Autoset amp**: `07`  
- **Background cal / remove**: `0D` / `0E`  
- **Restart HP**: `19` (if supported)  
- **Factory reset**: `FF 52 45 53 45 54` (“RESET”)

**Status codes (examples)**: `01=Success`, `02=Success weak signal`, `FF=Error`, `FC=Range error`, `FB=Forbidden`, `FA=No target`, `F9=Target lost (HP)`.

---

## Practical Tips

- Combine **Distance (16)** with **MeasCount (128)** when debugging drops.  
- For **handheld mapping**, prefer Profile **3** (Close) indoors, and set **Outlier** limits to kill jitter.  
- Use **Distance Offset** to zero your rig against a reference plane; then **Save** the parameters.
- When switching to heavy payload (Spectrum/IQ), step baud up first, then change **Selector**.

---

## License

MIT for this README content. Sensor firmware & protocol docs are © by OndoSense.
