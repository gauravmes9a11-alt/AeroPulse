# Series Hybrid-Electric UAV Propulsion Optimization

This project is a complete simulation and multi-objective optimization framework for a 1000 kg-class fixed-wing UAV with a series hybrid-electric propulsion chain:

`Fuel tank -> gas turbine -> generator -> DC bus <-> battery -> inverter/motor -> propeller`

The code is intentionally modular: `models.py` contains replaceable subsystem curves, `ems.py` contains pluggable energy-management strategies, `mission_sim.py` performs the one-Hz mission integration, and `optimize.py` runs NSGA-II to produce a Pareto set rather than a single hardcoded design.

It also includes a professional Streamlit dashboard for interactive mission simulation, timeline visualization, Pareto exploration, sensitivity review, and design-summary export.

For live simulation of this Series Hybrid-Electric UAV Propulsion Architecture use the below link:

(Aeropulse-simulation(https://aero-pulse-simulation.vercel.app/)

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

The required libraries are `numpy`, `scipy`, `pymoo`, `matplotlib`, and `pandas`.

## Run Dashboard

```bash
streamlit run app.py
```

The dashboard is structured as:

- `app.py`: Streamlit entry point, page router, theme toggle, and shared sidebar configuration
- `pages/mission_overview.py`: hardware/EMS configuration and simulation KPIs
- `pages/mission_timeline.py`: synchronized Plotly mission charts
- `pages/optimization_pareto.py`: Pareto CSV loader, NSGA-II trigger, parallel coordinates, scatter matrix, and selectable table
- `pages/sensitivity_analysis.py`: tornado-style sensitivity plots
- `pages/design_summary_export.py`: current design summary, PDF export, and CSV downloads
- `components/`: reusable Plotly chart, theme, and export helpers
- `utils/data_loader.py`: cached wrappers around the backend simulation and optimizer

If `outputs/pareto_front.csv` does not exist yet, the Pareto Explorer shows an empty state instead of crashing. You can create it from the dashboard with **Re-optimize** or from the CLI with `python main.py --pop 48 --gens 40`.

## Run Baseline Validation

```bash
python main.py --skip-optimization
```

This runs the baseline hardware and Tier 1 rule-based EMS:

- 60 kW turbine
- 65 kW generator
- 120 kW motor
- 65 kW battery peak power
- battery capacity and fuel mass from `HardwareConfig`

The CLI prints mission success, first violated constraint if any, endurance, fuel burned, final SoC, average efficiency, degradation proxy, and a climb-segment energy balance.

## Run Full Optimization

```bash
python main.py --pop 48 --gens 40
```

For a quick smoke run:

```bash
python main.py --pop 12 --gens 4
```

Outputs are written to `outputs/`:

- `pareto_front.csv`: objective values and design variables for non-dominated candidates
- `hypervolume_log.csv`: hypervolume convergence by generation
- `mission_timeline.png`
- `soc_profile.png`
- `fuel_remaining.png`
- `power_split.png`
- `pareto_parallel_coordinates.png`

## Pareto Front Interpretation

The optimizer minimizes five objectives:

- `neg_endurance_h`, which is `-endurance` so that longer endurance is better
- `fuel_burned_kg`
- `degradation_proxy`
- `neg_efficiency`, which is `-mission_avg_efficiency` so that higher efficiency is better
- `total_mass_kg`

The CSV also includes readable columns such as `endurance_h`, `efficiency`, `ems_tier`, hardware ratings, EMS setpoints, SoC bands, and first-violation diagnostics.

There is no single final answer configuration baked into the code. `select_knee_point()` in `optimize.py` provides one documented compromise method: normalize all objectives and choose the design closest to the utopia point. HAL engineers can replace this with mission-weighted scoring, minimum-endurance filters, or program-specific constraints.

## Sensitivity

Run fixed-baseline one-parameter-at-a-time sweeps from Python:

```python
from sensitivity import run_fixed_baseline_sensitivity
run_fixed_baseline_sensitivity("outputs")
```

To re-run the optimizer for each perturbation:

```python
from sensitivity import run_optimizer_sensitivity
run_optimizer_sensitivity("outputs")
```

The sensitivity module varies turbine SFC, battery specific energy, and motor/inverter efficiency, then reports percent shifts in each objective.

## Multi-Motor Propulsion

The `num_motors` design variable controls how many propulsion motors share the total 120 kW motor rating. Candidate values are **1, 2, or 4**.

### Motor Efficiency

When `num_motors > 1`, each motor is sized to `motor_rating / N`. The existing quadratic roll-off efficiency curve is evaluated per-motor, using both the per-motor load (`P_total / N`) and the per-motor rated power (`P_rated / N`). This means splitting the load does **not** automatically improve efficiency — it depends on where each motor operates on its efficiency curve.

### Motor Mass Model

Smaller motors carry proportionally more fixed overhead mass (mounts, connectors, controller housing). A non-linear power-law model is used:

```
mass_per_motor = a * rated_power^b + c_fixed
total_motor_mass = N * mass_per_motor(motor_rating / N)
```

The constants `a = 0.18`, `b = 0.85`, `c_fixed = 2.0 kg` are tunable engineering assumptions in `models.py::motor_mass_per_unit()`. When `N == 1`, the original linear specific-power model is used for exact backward compatibility.

### Motor Allocation Strategies

Two allocation strategies are available (configured in the sidebar under **Power Sharing Strategy**):

| Strategy | Behavior |
|----------|----------|
| **Even Split** | All N motors share load equally at all times. |
| **Efficiency-Optimal** | During low-power segments (Cruise, Loiter, Descent), motors may be shut down to keep active motors closer to peak efficiency. Minimum 1 active motor; per-motor peak power limits are respected. All motors are always active during Takeoff and Climb. |

### NSGA-II Integration

The optimizer treats `num_motors` as a categorical design variable with candidates `{1, 2, 4}`, encoded as a continuous proxy and discretized during decode. The mass objective (f5) uses the N-dependent motor mass calculation.

**Redundancy note:** `N ≥ 2` enables single-motor-failure survivability, surfaced as a qualitative note (`redundancy_note` column) in Pareto results. A 6th "redundancy score" objective can be added if needed (see code comment in `optimize.py::decode_design`).

## Power Sharing Strategy (Sidebar)

The sidebar is organized into two visually separated sections reflecting the design-variable vs. decision-variable distinction:

### Hardware Sizing (Design Variables)

Physical component ratings optimized by NSGA-II: turbine, generator, battery capacity/peak power, fuel mass, and **number of propulsion motors**.

### Power Sharing Strategy (Decision Variables)

Operational settings that control how power is distributed during flight:

- **EMS Tier**: Rule-Based / ECMS / Offline-Optimal
- **Generator Target Setpoint** (Rule-Based only): bounded to `[50% × gen_rating, gen_rating]`
- **Target SoC Band**: range slider for min/max battery charge targets
- **Max Charge C-Rate**: how fast the generator may recharge the battery
- **ECMS Equivalence Factor** (ECMS only): fuel-equivalent penalty for battery use
- **Motor Allocation Strategy** (multi-motor only): Even Split or Efficiency-Optimal

## Assumptions to Review

The mission powers and baseline component ratings are treated as given Section 5.1 data. Efficiency, SFC, battery specific energy, round-trip efficiency, DC bus loss, and degradation coefficients are adjustable Section 5.2 assumptions in `ModelAssumptions`.

Mission segment durations were not specified in the prompt, so `MissionProfile` makes them explicit adjustable defaults:

- takeoff: 120 s
- climb: 900 s
- cruise: 7200 s
- loiter: extended until a constraint binds
- descent: 600 s
- landing: 180 s
