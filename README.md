# SCAPS Validation Project

## Overview

This project automates the validation of perovskite solar cell simulations using **SCAPS** (Solar Cell Absorption Parameter Set). It generates batch simulation scripts for testing multiple device configurations and validates their performance through IV (current-voltage) curve analysis.

## Project Structure

```
scaps validation/
├── baseSim.scaps                          # Base SCAPS simulation file
├── extracted_simulation_data.csv          # Simulation parameters dataset
├── generate_batch.py                      # Python script to generate SCAPS batch files
├── validate_all_simulations.script        # Master validation script
├── validate_simulations_part1.script      # Part 1 of validation (perovskite layer 1)
├── validate_simulations_part2.script      # Part 2 of validation (perovskite layer 2)
├── validate_simulations_part3.script      # Part 3 of validation (perovskite layer 3)
└── README.md                              # This file
```

## Files Description

### Core Files

- **baseSim.scaps**: The template SCAPS definition file that defines the basic device structure (3-layer perovskite solar cell)
- **extracted_simulation_data.csv**: CSV file containing simulation parameter configurations:
  - `simulation_id`: Unique identifier for each simulation
  - `L1_L`, `L1_N_D`, `L1_N_A`: Layer 1 (ETL/PCBM) thickness and doping
  - `L2_L`, `L2_N_D`, `L2_N_A`: Layer 2 (Perovskite Absorber) thickness and doping
  - `L3_L`, `L3_N_D`, `L3_N_A`: Layer 3 (HTL/PEDOT) thickness and doping

### Python Script

- **generate_batch.py**: Generates SCAPS batch scripts from CSV data
  - Reads simulation parameters from CSV
  - Creates SCAPS script files with parameter sets
  - Generates IV curve output files for each simulation
  - Splits simulations into 3 parts for batch processing

### Validation Scripts

- **validate_all_simulations.script**: Master SCAPS script that runs all configurations
- **validate_simulations_part1.script**: Batch 1 - Configurations for Layer 1 validation
- **validate_simulations_part2.script**: Batch 2 - Configurations for Layer 2 validation
- **validate_simulations_part3.script**: Batch 3 - Configurations for Layer 3 validation

## Device Architecture

The simulations model a 3-layer perovskite solar cell:

```
Layer 1: ETL (PCBM)           - Electron Transport Layer
  ├─ Thickness (L)
  ├─ Donor Doping (N_D)
  └─ Acceptor Doping (N_A)

Layer 2: Perovskite Absorber  - Light Absorbing Layer
  ├─ Thickness (L)
  ├─ Donor Doping (N_D)
  └─ Acceptor Doping (N_A)

Layer 3: HTL (PEDOT)          - Hole Transport Layer
  ├─ Thickness (L)
  ├─ Donor Doping (N_D)
  └─ Acceptor Doping (N_A)
```

## Workflow

### 1. Generate Batch Scripts

```bash
python generate_batch.py
```

**What it does:**
- Reads all configurations from `extracted_simulation_data.csv`
- Generates SCAPS script commands for each configuration
- Creates 3 batch scripts based on data chunks
- Each script contains `load`, `set`, `calculate`, and `save` commands

### 2. Run Simulations in SCAPS

- Load the generated batch scripts in SCAPS application
- The scripts will:
  - Load the base simulation definition
  - Set layer parameters for each configuration
  - Calculate device performance (IV curves)
  - Save IV curve data for each simulation ID

### 3. Validate Results

- IV curve files are saved as `{simulation_id}_validation.iv`
- Results can be analyzed for performance metrics:
  - Short-circuit current (Jsc)
  - Open-circuit voltage (Voc)
  - Fill factor (FF)
  - Power conversion efficiency (PCE)

## SCAPS Script Commands Reference

| Command | Purpose |
|---------|---------|
| `clear` | Clear the current workspace |
| `load definitionfile` | Load the base device structure |
| `action.iv` | Enable/disable IV curve calculation |
| `set layer(x).thickness` | Set layer thickness (in meters) |
| `set layer(x).nd` | Set layer donor doping concentration |
| `set layer(x).na` | Set layer acceptor doping concentration |
| `calculate` | Perform simulation calculation |
| `save results.iv` | Save IV curve results |

## Usage Example

1. **Prepare your data** - Ensure `extracted_simulation_data.csv` contains all required parameters
2. **Generate scripts** - Run `python generate_batch.py`
3. **Load in SCAPS** - Open SCAPS and run the generated validation scripts
4. **Collect results** - Extract `.iv` files and analyze performance data

## Notes

- Each simulation ID should be unique for proper result file organization
- Layer parameters use SI units (meters for thickness, cm⁻³ for doping)
- The three-part split allows for parallel or sequential processing of large batches
- IV curve files are generated in SCAPS native format for further analysis

## Requirements

- SCAPS simulation software (for running `.script` files)
- Python 3.x with `pandas` library (for generating batch scripts)
- CSV file with properly formatted simulation parameters

## Future Enhancements

- Automated results parsing from `.iv` files
- Performance metric extraction (Jsc, Voc, FF, PCE)
- Result visualization and comparison
- Parameter optimization algorithms
