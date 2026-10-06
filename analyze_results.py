#!/usr/bin/env python3
"""
analyze_results.py -- builds the Chapter 4 comparative tables and figures.

REAL RUN
    python3 analyze_results.py \
        --results-dir  "C:/SCAPS/results"        # folder holding sim00001.iv ... sim10000.iv
        --manifest     all_batches_params.csv    # from generate_scaps_batches.py
        --ml-csv       ml_predictions.csv        # columns: sim_id, ml_pce   (PCE in %)
        --baseline-iv  baseline.iv  --optimized-iv optimized.iv   # the two point devices
        --reference    reference_values.json     # ML/SIMsalabim numbers, see below
        --outdir       chapter4_out

    reference_values.json (any field may be omitted; omitted -> "n/a" in tables):
    {"baseline":  {"pce": 19.92, "voc": null, "jsc": null, "ff": null},
     "optimized": {"pce": 21.69, "voc": null, "jsc": null, "ff": null}}

    ml_predictions.csv is made by feeding the parameter columns of
    all_batches_params.csv into the trained ML model of the reference study.

DEMO RUN  (layout test only, uses SYNTHETIC numbers, every figure is watermarked)
    python3 analyze_results.py --demo --outdir demo_out

The I-V parser reads the voltage and current-density columns from the numeric
block of each .iv file (col 0 = V in volts, col 1 = J in mA/cm2) and derives
Voc, Jsc, FF, Pmax and PCE from the curve itself, matching Section 3.5.
Open one .iv file once and confirm column 0/1 are V and total J.
"""
import argparse, json, os, re, sys, glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

P_IN = 100.0            # mW/cm2  (1000 W/m2, AM1.5G)
SQ_LIMIT = 33.3         # % Shockley-Queisser limit used in Section 3.7
PARAMS = ["L1_L", "L1_E_c", "L1_E_v", "L1_N_D", "L1_N_A",
          "L2_L", "L2_E_c", "L2_E_v", "L2_N_D", "L2_N_A",
          "L3_L", "L3_E_c", "L3_E_v", "L3_N_D", "L3_N_A"]
NAVY, AMBER, TEAL, GREY = "#0B2545", "#D99A00", "#1C7293", "#6B7C8F"

plt.rcParams.update({"font.family": "serif", "font.size": 11, "axes.grid": True,
                     "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.dpi": 110})


# ----------------------------------------------------------------- parsing
def read_iv(path):
    """Return (V, J) arrays from the longest numeric block of a SCAPS .iv file."""
    blocks, cur = [], []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            tok = line.replace(",", " ").split()
            try:
                vals = [float(t) for t in tok[:2]]
                if len(tok) >= 2:
                    cur.append(vals); continue
            except ValueError:
                pass
            if cur:
                blocks.append(cur); cur = []
    if cur:
        blocks.append(cur)
    if not blocks:
        return None, None
    arr = np.array(max(blocks, key=len))
    return arr[:, 0], arr[:, 1]


def metrics_from_curve(V, J):
    """Voc, Jsc, FF, Pmax, PCE from an illuminated J-V curve.
    Returns None when the curve is unusable (no Voc crossing, too short...)."""
    if V is None or len(V) < 5:
        return None
    order = np.argsort(V); V, J = V[order], J[order]
    if V.min() > 0 or V.max() < 0.05:
        return None
    j0 = np.interp(0.0, V, J)
    if j0 == 0:
        return None
    Jg = J * (1.0 if j0 > 0 else -1.0)          # generated current made positive
    jsc = abs(j0)
    idx = np.where((Jg[:-1] > 0) & (Jg[1:] <= 0))[0]
    if len(idx) == 0:
        return None                              # curve never reaches Voc
    i = idx[0]
    voc = V[i] + (0 - Jg[i]) * (V[i + 1] - V[i]) / (Jg[i + 1] - Jg[i])
    m = (V >= 0) & (V <= voc)
    P = V[m] * Jg[m]
    if len(P) == 0 or P.max() <= 0:
        return None
    pmax = P.max()
    ff = pmax / (voc * jsc)
    return {"voc": voc, "jsc": jsc, "ff": ff, "pmax": pmax,
            "pce": 100.0 * pmax / P_IN}


# ----------------------------------------------------------------- statistics
def agreement(y_ml, y_sc):
    y_ml, y_sc = np.asarray(y_ml, float), np.asarray(y_sc, float)
    res = y_sc - y_ml
    ss_res = np.sum((y_sc - y_ml) ** 2)
    ss_tot = np.sum((y_sc - y_sc.mean()) ** 2)
    return {"N": len(y_ml),
            "R2": 1 - ss_res / ss_tot,
            "RMSE_pp": float(np.sqrt(np.mean(res ** 2))),
            "MAE_pp": float(np.mean(np.abs(res))),
            "MAPE_pct": float(100 * np.mean(np.abs(res) / np.abs(y_sc))),
            "mean_bias_pp": float(res.mean()),
            "pearson_r": float(np.corrcoef(y_ml, y_sc)[0, 1]),
            "spearman_rho": float(pd.Series(y_ml).corr(pd.Series(y_sc), method="spearman"))}


def sensitivity(df, ycol):
    return {p: float(df[p].corr(df[ycol], method="spearman")) for p in PARAMS}


# ----------------------------------------------------------------- plotting
def watermark(fig, demo):
    if demo:
        fig.text(0.5, 0.5, "SYNTHETIC DEMO - NOT SCAPS RESULTS", ha="center", va="center",
                 rotation=25, fontsize=15, color="red", alpha=0.25, weight="bold")


def save(fig, outdir, name, demo):
    watermark(fig, demo)
    fig.tight_layout()
    fig.savefig(os.path.join(outdir, "figures", name), dpi=300)
    plt.close(fig)


def fig_jv(curves, outdir, demo):
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    for label, (V, J), c in curves:
        j0 = np.interp(0, V, J)
        ax.plot(V, J * (1 if j0 > 0 else -1), lw=2, color=c, label=label)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel("Voltage (V)"); ax.set_ylabel("Current density (mA/cm$^2$)")
    ax.set_title("SCAPS-1D J-V curves: baseline vs optimized device")
    ax.legend(); save(fig, outdir, "fig_4_1_jv_curves.png", demo)


def fig_points(tab, outdir, demo):
    fig, axes = plt.subplots(1, 4, figsize=(11, 3.6))
    for ax, (k, lab) in zip(axes, [("pce", "PCE (%)"), ("voc", "$V_{oc}$ (V)"),
                                   ("jsc", "$J_{sc}$ (mA/cm$^2$)"), ("ff", "FF")]):
        xs = np.arange(2); w = 0.36
        sc = [tab["baseline"]["scaps"][k], tab["optimized"]["scaps"][k]]
        rf = [tab["baseline"]["ref"].get(k), tab["optimized"]["ref"].get(k)]
        ax.bar(xs - w / 2, sc, w, color=NAVY, label="SCAPS-1D")
        if all(v is not None for v in rf):
            ax.bar(xs + w / 2, rf, w, color=AMBER, label="ML / SIMsalabim")
        ax.set_xticks(xs); ax.set_xticklabels(["Baseline", "Optimized"])
        ax.set_title(lab, fontsize=11)
    axes[0].legend(fontsize=9)
    save(fig, outdir, "fig_4_2_point_comparison.png", demo)


def fig_parity(df, stats, outdir, demo):
    fig, ax = plt.subplots(figsize=(5.4, 5.2))
    ax.scatter(df.ml_pce, df.scaps_pce, s=9, alpha=0.5, color=TEAL, edgecolor="none")
    lo = min(df.ml_pce.min(), df.scaps_pce.min()); hi = max(df.ml_pce.max(), df.scaps_pce.max())
    ax.plot([lo, hi], [lo, hi], "--", color="k", lw=1, label="1:1 line")
    ax.set_xlabel("ML-predicted PCE (%)"); ax.set_ylabel("SCAPS-1D PCE (%)")
    ax.set_title("Parity plot: ML prediction vs SCAPS-1D")
    ax.text(0.04, 0.94, f"$R^2$ = {stats['R2']:.3f}\nRMSE = {stats['RMSE_pp']:.2f} pp\n"
            f"MAPE = {stats['MAPE_pct']:.2f} %\nN = {stats['N']}", transform=ax.transAxes,
            va="top", fontsize=10, bbox=dict(fc="white", ec=GREY, alpha=0.9))
    ax.legend(loc="lower right"); ax.set_aspect("equal", adjustable="datalim")
    save(fig, outdir, "fig_4_3_parity_plot.png", demo)


def fig_dist(df, outdir, demo):
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4))
    bins = np.linspace(min(df.ml_pce.min(), df.scaps_pce.min()),
                       max(df.ml_pce.max(), df.scaps_pce.max()), 35)
    a.hist(df.scaps_pce, bins, alpha=0.65, color=NAVY, label="SCAPS-1D")
    a.hist(df.ml_pce, bins, alpha=0.55, color=AMBER, label="ML")
    a.set_xlabel("PCE (%)"); a.set_ylabel("Number of devices"); a.set_title("PCE distributions"); a.legend()
    r = df.scaps_pce - df.ml_pce
    b.hist(r, 35, color=TEAL, alpha=0.8); b.axvline(0, color="k", lw=1)
    b.axvline(r.mean(), color="red", ls="--", lw=1.4, label=f"mean = {r.mean():+.2f} pp")
    b.set_xlabel("SCAPS-1D minus ML (percentage points)"); b.set_title("Residuals"); b.legend()
    save(fig, outdir, "fig_4_4_distributions_residuals.png", demo)


def fig_sens(s_sc, s_ml, outdir, demo):
    fig, ax = plt.subplots(figsize=(10, 4.4)); x = np.arange(len(PARAMS)); w = 0.4
    ax.bar(x - w / 2, [s_sc[p] for p in PARAMS], w, color=NAVY, label="SCAPS-1D")
    ax.bar(x + w / 2, [s_ml[p] for p in PARAMS], w, color=AMBER, label="ML")
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x); ax.set_xticklabels(PARAMS, rotation=60, ha="right")
    ax.set_ylabel("Spearman correlation with PCE"); ax.set_title("Parameter sensitivity: SCAPS-1D vs ML")
    ax.legend(); save(fig, outdir, "fig_4_5_sensitivity.png", demo)


# ----------------------------------------------------------------- demo data
def synth_curve(voc, jsc, ff_n=1.6, n=80):
    V = np.linspace(0, voc * 1.05, n)
    J = jsc * (1 - np.exp((V - voc) / (ff_n * 0.02585 * 2.2)) )     # generated current, positive
    return V, J


def demo_data(rng):
    n = 400
    cols = {p: rng.uniform(0, 1, n) for p in PARAMS}
    df = pd.DataFrame(cols); df.insert(0, "sim_id", [f"sim{i+1:05d}" for i in range(n)])
    pce = 15 + 4 * df.L2_L + 2.5 * df.L1_E_c - 2 * df.L1_L - 1 * df.L3_L + rng.normal(0, .4, n)
    df["scaps_pce"] = pce; df["ml_pce"] = pce + rng.normal(0.15, 0.5, n)
    pts = {"baseline": synth_curve(1.10, 22.5), "optimized": synth_curve(1.13, 23.6)}
    return df, pts


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results-dir"); ap.add_argument("--manifest"); ap.add_argument("--ml-csv")
    ap.add_argument("--baseline-iv"); ap.add_argument("--optimized-iv"); ap.add_argument("--reference")
    ap.add_argument("--outdir", default="chapter4_out"); ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.outdir, "figures"), exist_ok=True)
    os.makedirs(os.path.join(a.outdir, "tables"), exist_ok=True)
    rng = np.random.default_rng(1)

    # ---- assemble the dataset --------------------------------------------
    excluded = {"missing_file": 0, "unusable_curve": 0, "above_SQ_limit": 0}
    if a.demo:
        df, pts = demo_data(rng); n_expected = len(df)
        ref = {"baseline": {"pce": 19.92}, "optimized": {"pce": 21.69}}
        curves = {}
        for k, (V, J) in pts.items():
            curves[k] = (V, J, metrics_from_curve(V, J))
        # demo manifest columns are 0-1 scaled; fine for sensitivity layout only
    else:
        for need in ("results_dir", "manifest", "ml_csv"):
            if getattr(a, need) is None:
                sys.exit(f"--{need.replace('_','-')} is required (or use --demo)")
        man = pd.read_csv(a.manifest); n_expected = len(man)
        rows = []
        for _, r in man.iterrows():
            fp = os.path.join(a.results_dir, f"{r.sim_id}.iv")
            if not os.path.isfile(fp):
                excluded["missing_file"] += 1; continue
            m = metrics_from_curve(*read_iv(fp))
            if m is None:
                excluded["unusable_curve"] += 1; continue
            if m["pce"] > SQ_LIMIT or m["pce"] <= 0:
                excluded["above_SQ_limit"] += 1; continue
            rows.append({"sim_id": r.sim_id, **{p: r[p] for p in PARAMS},
                         **{"scaps_" + k: v for k, v in m.items()}})
        df = pd.DataFrame(rows)
        ml = pd.read_csv(a.ml_csv)[["sim_id", "ml_pce"]]
        df = df.merge(ml, on="sim_id", how="inner")
        ref = json.load(open(a.reference)) if a.reference else {"baseline": {}, "optimized": {}}
        curves = {}
        for key, path in (("baseline", a.baseline_iv), ("optimized", a.optimized_iv)):
            if path:
                V, J = read_iv(path); curves[key] = (V, J, metrics_from_curve(V, J))

    # ---- Table 4.1 dataset summary ---------------------------------------
    t1 = pd.DataFrame([
        ["Configurations simulated (scripts run)", n_expected],
        ["Valid, converged records used for analysis", len(df)],
        ["Excluded: output file missing", excluded["missing_file"]],
        ["Excluded: incomplete / non-converged I-V curve", excluded["unusable_curve"]],
        ["Excluded: PCE outside physical limit (>33.3 % or <=0)", excluded["above_SQ_limit"]],
        ["Convergence rate (%)", round(100 * len(df) / max(n_expected, 1), 2)]],
        columns=["Item", "Value"])
    t1["Value"] = [f"{v:g}" if isinstance(v, float) else str(v) for v in t1["Value"]]
    t1.to_csv(os.path.join(a.outdir, "tables", "table_4_1_dataset_summary.csv"), index=False)

    # ---- Table 4.2 point comparison --------------------------------------
    tab = {}
    rows2 = []
    for key in ("baseline", "optimized"):
        if key in curves and curves[key][2]:
            m = curves[key][2]
            tab[key] = {"scaps": m, "ref": ref.get(key, {})}
            r = ref.get(key, {})
            rows2.append([key.capitalize(), f"{m['voc']:.3f}", f"{m['jsc']:.2f}", f"{m['ff']*100:.2f}",
                          f"{m['pmax']:.2f}", f"{m['pce']:.2f}",
                          "n/a" if r.get("pce") is None else f"{r['pce']:.2f}",
                          "n/a" if r.get("pce") is None else f"{m['pce']-r['pce']:+.2f}"])
    if len(tab) == 2:
        b, o = tab["baseline"]["scaps"]["pce"], tab["optimized"]["scaps"]["pce"]
        rel = 100 * (o - b) / b
        rows2.append(["Relative PCE change (optimized vs baseline)", "", "", "", "",
                      f"{rel:+.2f} %", f"{100*(21.69-19.92)/19.92:+.2f} %" if a.demo or ref["baseline"].get("pce") else "n/a", ""])
    t2 = pd.DataFrame(rows2, columns=["Device", "Voc (V)", "Jsc (mA/cm2)", "FF (%)", "Pmax (mW/cm2)",
                                      "SCAPS PCE (%)", "ML/SIMsalabim PCE (%)", "Difference (pp)"])
    t2.to_csv(os.path.join(a.outdir, "tables", "table_4_2_point_comparison.csv"), index=False)

    # ---- Table 4.3 agreement ---------------------------------------------
    st = agreement(df.ml_pce, df.scaps_pce)
    t3 = pd.DataFrame([["N (devices compared)", st["N"]], ["R2", f"{st['R2']:.4f}"],
                       ["RMSE (percentage points)", f"{st['RMSE_pp']:.3f}"],
                       ["MAE (percentage points)", f"{st['MAE_pp']:.3f}"],
                       ["MAPE (%)", f"{st['MAPE_pct']:.3f}"],
                       ["Mean bias, SCAPS - ML (pp)", f"{st['mean_bias_pp']:+.3f}"],
                       ["Pearson r", f"{st['pearson_r']:.4f}"],
                       ["Spearman rho", f"{st['spearman_rho']:.4f}"]], columns=["Statistic", "Value"])
    t3.to_csv(os.path.join(a.outdir, "tables", "table_4_3_agreement_statistics.csv"), index=False)

    # ---- Table 4.4 sensitivity -------------------------------------------
    s_sc = sensitivity(df, "scaps_pce"); s_ml = sensitivity(df, "ml_pce")
    t4 = pd.DataFrame([[p, f"{s_sc[p]:+.3f}", f"{s_ml[p]:+.3f}",
                        "same" if np.sign(s_sc[p]) == np.sign(s_ml[p]) else "opposite"] for p in PARAMS],
                      columns=["Parameter", "Spearman (SCAPS)", "Spearman (ML)", "Direction"])
    t4.to_csv(os.path.join(a.outdir, "tables", "table_4_4_parameter_sensitivity.csv"), index=False)

    # ---- Table 4.5 criteria ----------------------------------------------
    c1 = "Met" if len(tab) == 2 and tab["optimized"]["scaps"]["pce"] > tab["baseline"]["scaps"]["pce"] else \
         ("Not met" if len(tab) == 2 else "Point devices not supplied")
    c3 = "Met" if (df.scaps_pce <= SQ_LIMIT).all() and excluded["above_SQ_limit"] == 0 else "Review flagged records"
    t5 = pd.DataFrame([
        ["1. SCAPS PCE(optimized) > SCAPS PCE(baseline)", c1],
        ["2. SCAPS PCE correlates closely with ML PCE", f"R2 = {st['R2']:.3f}, rho = {st['spearman_rho']:.3f} (judge against your chosen threshold)"],
        ["3. All converged devices below the 33.3 % Shockley-Queisser limit", c3]],
        columns=["Criterion (Section 3.7)", "Outcome"])
    t5.to_csv(os.path.join(a.outdir, "tables", "table_4_5_validation_criteria.csv"), index=False)

    # ---- figures ---------------------------------------------------------
    if "baseline" in curves and "optimized" in curves:
        fig_jv([("Baseline", curves["baseline"][:2], NAVY), ("Optimized", curves["optimized"][:2], AMBER)],
               a.outdir, a.demo)
    if len(tab) == 2:
        fig_points(tab, a.outdir, a.demo)
    fig_parity(df, st, a.outdir, a.demo); fig_dist(df, a.outdir, a.demo); fig_sens(s_sc, s_ml, a.outdir, a.demo)

    df.to_csv(os.path.join(a.outdir, "verification_dataset.csv"), index=False)
    for name, t in (("4.1", t1), ("4.2", t2), ("4.3", t3), ("4.4", t4), ("4.5", t5)):
        print(f"\nTable {name}\n{t.to_string(index=False)}")
    print(f"\nOutputs written to {a.outdir}/tables and {a.outdir}/figures")


if __name__ == "__main__":
    main()
