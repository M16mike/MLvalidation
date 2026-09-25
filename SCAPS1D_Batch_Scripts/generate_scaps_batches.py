#!/usr/bin/env python3
"""
generate_scaps_batches.py

Generates 10 SCAPS-1D script files (SCAPS 3.0.02 script language), each running
~1000 physics-validated device configurations sampled from the 15-parameter
bounds in Table 3.1 (ITO/PCBM/MAPI/PEDOT:PSS/Au device stack).

Each configuration is checked against the same physics-validation rules
described in the methodology (Section 3.4.3) before a script block is written
for it:
    1. Positive band gap in every layer (Eg = Ev - Ec > 0).
    2. ETL conduction band at/above the absorber conduction band, so
       electrons cascade toward the ETL.
    3. HTL valence band at/below the absorber valence band, so holes
       cascade toward the HTL.
    4. Transport layers stay thin, the absorber stays thick (guaranteed by
       the disjoint bounds, checked explicitly anyway).

SCAPS command reference used here (SCAPS 3.0.02 script manual,
https://scaps.elis.ugent.be/SCAPS%203002%20script%20manual.pdf):
    load definitionfile <file>      -- loads the baseline .def problem file
    set layer{n}.thickness <um>     -- layer thickness, MICROMETRES
    set layer{n}.chi <eV>           -- electron affinity == "conduction
                                        band edge" (Ec) in Table 3.1
    set layer{n}.Eg <eV>            -- band gap; SCAPS has no separate "Ev"
                                        input, so Eg = Ev - Ec is derived here
    set layer{n}.ND <cm-3>          -- donor concentration (table is in m-3!)
    set layer{n}.NA <cm-3>          -- acceptor concentration (table is m-3!)
    action iv.doiv                  -- enable the I-V sweep action
    calculate singleshot            -- run one simulation
    save results.iv <file>          -- write the I-V curve + Voc/Jsc/FF/eta
                                        header for that simulation
    clear simulations               -- free SCAPS's internal result buffer

IMPORTANT — before running these scripts in SCAPS, you must already have a
baseline .def problem file (see --defname) saved in scaps\\def, built once
through the SCAPS GUI, with:
    - the ITO/PCBM/MAPI/PEDOT:PSS/Au stack (layer1=PCBM, layer2=MAPI,
      layer3=PEDOT:PSS between the ITO front and Au back contact)
    - electrode work functions fixed to the reference-project values
    - the AM1.5G spectrum file loaded, illumination ON
    - the IV sweep window (start/stop voltage, points) set as intended
This generator only overrides the 15 sampled layer parameters each run; it
does not set up contacts, mesh, or illumination.
"""

import argparse
import csv
import os
import numpy as np

# ---------------------------------------------------------------------------
# Table 3.1 — parameter bounds, in the ORIGINAL units used in the thesis
# (nm for thickness, eV for band edges, m-3 for doping concentrations).
# ---------------------------------------------------------------------------
BOUNDS = {
    # ETL (PCBM) -- layer1
    "L1_L":   (20, 50),          # nm
    "L1_E_c": (3.8, 4.0),        # eV
    "L1_E_v": (5.8, 6.0),        # eV
    "L1_N_D": (5e20, 1e21),      # m-3
    "L1_N_A": (1e19, 5e19),      # m-3
    # Absorber (MAPI) -- layer2
    "L2_L":   (210, 350),        # nm
    "L2_E_c": (3.6, 3.8),        # eV
    "L2_E_v": (5.4, 5.6),        # eV
    "L2_N_D": (1e16, 1e17),      # m-3
    "L2_N_A": (1e16, 1e17),      # m-3
    # HTL (PEDOT:PSS) -- layer3
    "L3_L":   (20, 50),          # nm
    "L3_E_c": (2.8, 3.2),        # eV
    "L3_E_v": (5.0, 5.2),        # eV
    "L3_N_D": (1e19, 5e19),      # m-3
    "L3_N_A": (5e20, 1e21),      # m-3
}

PARAM_ORDER = list(BOUNDS.keys())


def sample_one(rng):
    """Draw one uniform-random 15-parameter configuration from Table 3.1."""
    return {k: rng.uniform(lo, hi) for k, (lo, hi) in BOUNDS.items()}


def is_physically_valid(p):
    """Section 3.4.3 physics-validation rules, applied before a script block
    is written for this configuration."""
    # 1. positive band gap in every layer
    for L in ("L1", "L2", "L3"):
        if p[f"{L}_E_v"] - p[f"{L}_E_c"] <= 0:
            return False
    # 2. ETL conduction band at/above the absorber conduction band
    #    (electrons cascade toward the ETL)
    if not (p["L1_E_c"] >= p["L2_E_c"]):
        return False
    # 3. HTL valence band at/below the absorber valence band
    #    (holes cascade toward the HTL)
    if not (p["L3_E_v"] <= p["L2_E_v"]):
        return False
    # 4. transport layers thin, absorber thicker (redundant given the
    #    disjoint bounds above, kept explicit for traceability)
    if not (p["L2_L"] > p["L1_L"] and p["L2_L"] > p["L3_L"]):
        return False
    return True


def sample_n_valid(rng, n):
    """Rejection-sample until n physically-valid configurations are found.
    Returns the list of accepted configs and the number of rejects."""
    accepted = []
    rejects = 0
    while len(accepted) < n:
        p = sample_one(rng)
        if is_physically_valid(p):
            accepted.append(p)
        else:
            rejects += 1
    return accepted, rejects


def to_scaps_layer_commands(layer_num, p, prefix):
    """Convert one layer's Table-3.1 values (nm / eV / eV / m-3 / m-3) into
    the SCAPS `set layerN....` commands (um / eV / eV(Eg) / cm-3 / cm-3)."""
    thickness_um = p[f"{prefix}_L"] / 1000.0          # nm -> um
    chi_eV = p[f"{prefix}_E_c"]                        # Ec IS chi
    Eg_eV = p[f"{prefix}_E_v"] - p[f"{prefix}_E_c"]     # Eg = Ev - Ec
    ND_cm3 = p[f"{prefix}_N_D"] / 1e6                   # m-3 -> cm-3
    NA_cm3 = p[f"{prefix}_N_A"] / 1e6                   # m-3 -> cm-3
    L = f"layer{layer_num}"
    return [
        f"set {L}.thickness {thickness_um:.6f}",
        f"set {L}.chi {chi_eV:.4f}",
        f"set {L}.Eg {Eg_eV:.4f}",
        f"set {L}.ND {ND_cm3:.4E}",
        f"set {L}.NA {NA_cm3:.4E}",
    ]


def write_batch_script(path, def_name, configs, sim_ids):
    lines = []
    lines.append(f"! Auto-generated SCAPS-1D batch script -- {os.path.basename(path)}")
    lines.append(f"! {len(configs)} physics-validated device configurations")
    lines.append("! Layers: layer1=ETL(PCBM)  layer2=Absorber(MAPI)  layer3=HTL(PEDOT:PSS)")
    lines.append("")
    lines.append(f"load definitionfile {def_name}")
    lines.append("clear scriptvariables.all")
    lines.append("action light          ! illuminated I-V; verify AM1.5G spectrum is set in the .def")
    lines.append("action iv.doiv        ! enable the I-V sweep action")
    lines.append("")

    for sim_id, p in zip(sim_ids, configs):
        lines.append(f"! ---- {sim_id} ----")
        lines.extend(to_scaps_layer_commands(1, p, "L1"))
        lines.extend(to_scaps_layer_commands(2, p, "L2"))
        lines.extend(to_scaps_layer_commands(3, p, "L3"))
        lines.append("calculate singleshot")
        lines.append(f"save results.iv {sim_id}.iv")
        lines.append("clear simulations")
        lines.append("")

    with open(path, "w", newline="\n") as f:
        f.write("\n".join(lines))


def write_manifest(path, configs, sim_ids):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sim_id"] + PARAM_ORDER + ["iv_file"])
        for sim_id, p in zip(sim_ids, configs):
            w.writerow([sim_id] + [f"{p[k]:.6g}" for k in PARAM_ORDER] + [f"{sim_id}.iv"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-per-batch", type=int, default=1000)
    ap.add_argument("--n-batches", type=int, default=10)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--defname", type=str, default="perovskite_baseline.def",
                     help="Baseline .def problem file, already saved in scaps\\def")
    ap.add_argument("--outdir", type=str, default="./scaps_batches")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    global_index = 1
    total_rejects = 0
    all_rows = []

    for b in range(1, args.n_batches + 1):
        configs, rejects = sample_n_valid(rng, args.n_per_batch)
        total_rejects += rejects
        sim_ids = [f"sim{global_index + i:05d}" for i in range(len(configs))]
        global_index += len(configs)

        script_path = os.path.join(args.outdir, f"batch_{b:02d}.script")
        manifest_path = os.path.join(args.outdir, f"batch_{b:02d}_params.csv")
        write_batch_script(script_path, args.defname, configs, sim_ids)
        write_manifest(manifest_path, configs, sim_ids)

        for sim_id, p in zip(sim_ids, configs):
            all_rows.append((b, sim_id, p))

        print(f"batch_{b:02d}: {len(configs)} valid configs written "
              f"({rejects} rejected in this batch) -> {script_path}")

    # combined manifest across all 10 batches, for later analysis
    combined_path = os.path.join(args.outdir, "all_batches_params.csv")
    with open(combined_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["batch", "sim_id"] + PARAM_ORDER + ["iv_file"])
        for b, sim_id, p in all_rows:
            w.writerow([b, sim_id] + [f"{p[k]:.6g}" for k in PARAM_ORDER] + [f"{sim_id}.iv"])

    print(f"\nTotal valid configurations: {global_index - 1}")
    print(f"Total rejected by physics validation: {total_rejects} "
          f"({100 * total_rejects / (global_index - 1 + total_rejects):.2f}% reject rate)")
    print(f"Combined manifest: {combined_path}")


if __name__ == "__main__":
    main()
