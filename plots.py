"""Matplotlib plotting utilities for mission histories and Pareto fronts."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


def _plt():
    import matplotlib.pyplot as plt

    return plt


def plot_mission_timeline(history: Dict[str, np.ndarray], output_dir: str | Path) -> Path:
    plt = _plt()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    t = history["time_s"] / 3600.0
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(t, history["demand_kw"], lw=1.8, color="#1f77b4")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Propeller shaft demand (kW)")
    ax.set_title("Mission power timeline")
    _annotate_segments(ax, history)
    fig.tight_layout()
    path = out / "mission_timeline.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_soc_profile(history: Dict[str, np.ndarray], output_dir: str | Path) -> Path:
    plt = _plt()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(history["time_s"] / 3600.0, history["soc"], color="#2ca02c", lw=1.8)
    ax.axhline(0.20, color="#d62728", ls="--", lw=1)
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Battery SoC")
    ax.set_ylim(0, 1.05)
    ax.set_title("Battery state of charge")
    _annotate_segments(ax, history)
    fig.tight_layout()
    path = out / "soc_profile.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_fuel_remaining(history: Dict[str, np.ndarray], output_dir: str | Path) -> Path:
    plt = _plt()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(history["time_s"] / 3600.0, history["fuel_remaining_kg"], color="#9467bd", lw=1.8)
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Fuel remaining (kg)")
    ax.set_title("Fuel remaining")
    _annotate_segments(ax, history)
    fig.tight_layout()
    path = out / "fuel_remaining.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_power_split(history: Dict[str, np.ndarray], output_dir: str | Path) -> Path:
    plt = _plt()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    t = history["time_s"] / 3600.0
    gen = history["generator_kw"]
    batt_dis = np.maximum(history["battery_kw"], 0.0)
    batt_chg = np.minimum(history["battery_kw"], 0.0)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.stackplot(t, gen, batt_dis, labels=["Generator", "Battery discharge"], colors=["#1f77b4", "#ff7f0e"], alpha=0.75)
    ax.fill_between(t, 0, batt_chg, color="#2ca02c", alpha=0.45, label="Battery charge")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("Source-side power (kW)")
    ax.set_title("Generator and battery power split")
    ax.legend(loc="upper right")
    _annotate_segments(ax, history)
    fig.tight_layout()
    path = out / "power_split.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_pareto_front(pareto: pd.DataFrame, output_dir: str | Path) -> Path:
    plt = _plt()
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    cols = ["endurance_h", "fuel_burned_kg", "degradation_proxy", "efficiency", "total_mass_kg"]
    labels = ["Endurance", "Fuel", "Degradation", "Efficiency", "Mass"]
    data = pareto[cols].astype(float)
    norm = (data - data.min()) / (data.max() - data.min()).replace(0.0, 1.0)
    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(cols))
    for i, row in norm.iterrows():
        ax.plot(x, row.values, color="#1f77b4", alpha=0.25, lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Normalized value")
    ax.set_title("Pareto front parallel coordinates")
    fig.tight_layout()
    path = out / "pareto_parallel_coordinates.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def _annotate_segments(ax, history: Dict[str, np.ndarray]) -> None:
    segments = history["segment"]
    if len(segments) == 0:
        return
    times_h = history["time_s"] / 3600.0
    changes = np.where(segments[1:] != segments[:-1])[0] + 1
    starts = np.r_[0, changes]
    ends = np.r_[changes, len(segments) - 1]
    ymin, ymax = ax.get_ylim()
    for start, end in zip(starts, ends):
        mid = 0.5 * (times_h[start] + times_h[end])
        ax.axvline(times_h[start], color="0.85", lw=0.8)
        ax.text(mid, ymax, str(segments[start]), va="top", ha="center", fontsize=8, color="0.25")
