"""
plot_sessions.py — compare two uvula sessions side by side.

Usage:
    python3 plot_sessions.py session_log.csv 12 13
    python3 plot_sessions.py session_log.csv 12 13 --output comparison.png

Requires: matplotlib  (pip install matplotlib)
"""

import argparse
import csv
import sys
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

COLORS = ["#F4A020", "#4A90D9", "#50C878", "#E05A5A"]


def load_sessions(log_path, session_ids):
    data      = {sid: {"elapsed": [], "uvs": [], "cumulative": []} for sid in session_ids}
    summaries = {}

    with open(log_path, newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0] == "SUMMARY":
                try:
                    sid = int(row[1])
                except ValueError:
                    continue
                if sid in session_ids:
                    summaries[sid] = {
                        "elapsed_s":  int(row[5]),
                        "final_dose": int(row[6]),
                        "peak":       int(row[3]),
                        "min":        int(row[4]),
                        "status":     row[2],
                    }
            else:
                try:
                    sid = int(row[0])
                except ValueError:
                    continue
                if sid not in session_ids:
                    continue
                data[sid]["elapsed"].append(int(row[4]))
                data[sid]["uvs"].append(int(row[2]))
                data[sid]["cumulative"].append(int(row[3]))

    missing = [sid for sid in session_ids if not data[sid]["elapsed"]]
    if missing:
        print(f"Warning: no data found for session(s): {missing}", file=sys.stderr)

    return data, summaries


def plot(log_path, session_ids, output_path):
    data, summaries = load_sessions(log_path, session_ids)

    fig = plt.figure(figsize=(12, 8), facecolor="#0E0E0E")
    gs  = gridspec.GridSpec(2, 1, hspace=0.45, figure=fig)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    for ax in (ax1, ax2):
        ax.set_facecolor("#1A1A1A")
        ax.tick_params(colors="#AAAAAA")
        ax.xaxis.label.set_color("#AAAAAA")
        ax.yaxis.label.set_color("#AAAAAA")
        ax.title.set_color("#DDDDDD")
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")
        ax.grid(color="#2A2A2A", linestyle="--", linewidth=0.6)

    for i, sid in enumerate(session_ids):
        color = COLORS[i % len(COLORS)]
        s     = summaries.get(sid, {})
        dur   = s.get("elapsed_s",  data[sid]["elapsed"][-1]  if data[sid]["elapsed"]  else 0)
        dose  = s.get("final_dose", data[sid]["cumulative"][-1] if data[sid]["cumulative"] else 0)
        label = f"Session {sid}  ·  {dur}s  ·  dose {dose:,}"

        ax1.plot(data[sid]["elapsed"], data[sid]["uvs"],
                 color=color, linewidth=1.4, alpha=0.9, label=label)

        ax2.plot(data[sid]["elapsed"], data[sid]["cumulative"],
                 color=color, linewidth=1.8)
        if data[sid]["elapsed"]:
            ax2.annotate(
                f"S{sid}: {dose:,} in {dur}s",
                xy=(data[sid]["elapsed"][-1], data[sid]["cumulative"][-1]),
                xytext=(10, 10 * (1 if i % 2 == 0 else -1)),
                textcoords="offset points",
                color=color,
                fontsize=8.5,
                arrowprops=dict(arrowstyle="-", color=color, alpha=0.5),
            )

    ax1.set_title("UV reading per second", fontsize=12, pad=10)
    ax1.set_xlabel("Elapsed time (s)")
    ax1.set_ylabel("UVS counts / sec")
    ax1.legend(facecolor="#111111", edgecolor="#333333", labelcolor="#CCCCCC", fontsize=9)

    ax2.set_title("Cumulative UV dose", fontsize=12, pad=10)
    ax2.set_xlabel("Elapsed time (s)")
    ax2.set_ylabel("Cumulative UVS counts")

    session_str = " vs ".join(f"S{sid}" for sid in session_ids)
    fig.suptitle(f"uvula — {session_str}", color="#EEEEEE", fontsize=13, y=0.98)

    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print("Saved:", output_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Plot uvula session comparison")
    parser.add_argument("log",      help="Path to session_log.csv")
    parser.add_argument("sessions", nargs="+", type=int, help="Session IDs to compare")
    parser.add_argument("--output", default="uvula_comparison.png", help="Output PNG path")
    args = parser.parse_args()
    plot(args.log, args.sessions, args.output)
