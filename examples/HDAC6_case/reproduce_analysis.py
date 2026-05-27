#!/usr/bin/env python3
"""Reproduce forensic analysis of HDAC6 paper Source Data Fig.4
Usage: python reproduce_analysis.py --input <xlsx_path>"""
import argparse, numpy as np
from scipy import stats
from collections import Counter

def load_data(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb['Source Data Fig.4']
    raw = [list(r) for r in ws.iter_rows(values_only=True)]
    fig4c = np.array([[float(raw[i][j]) for j in range(1,9)] for i in range(4,39)])
    fig4f = np.array([[float(raw[i][j]) for j in range(10,16)] for i in range(4,39)])
    return fig4c, fig4f

def analyze_diffs(a, b, na, nb):
    diffs = np.round(b - a, 2)
    ud = Counter(diffs)
    print(f"\n{'='*50}")
    print(f"{nb} - {na}: {len(ud)} unique diffs in {len(diffs)} points")
    for d,c in sorted(ud.items()):
        print(f"  {d:+.2f}: {c} times ({c/len(diffs)*100:.1f}%)")
    # blocks
    blocks, cv, cs = [], diffs[0], 0
    for i in range(1, len(diffs)):
        if diffs[i] != cv:
            blocks.append((cs, i-1, cv)); cv, cs = diffs[i], i
    blocks.append((cs, len(diffs)-1, cv))
    print(f"Contiguous blocks: {len(blocks)}")
    for s,e,v in blocks:
        print(f"  Row {s+5}-{e+5} ({e-s+1} rows): {v:+.2f}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    args = p.parse_args()
    fig4c, fig4f = load_data(args.input)
    print("=" * 50)
    print("FORENSIC ANALYSIS: HDAC6 Paper Fig.4")
    print("=" * 50)
    # Smoking gun: 0h columns
    analyze_diffs(fig4c[:,2], fig4c[:,4], "shHDAC6_0h", "shTET2_0h")
    # Control: 24h
    analyze_diffs(fig4c[:,3], fig4c[:,5], "shHDAC6_24h", "shTET2_24h")
    # Fig4f
    analyze_diffs(fig4f[:,0], fig4f[:,3], "shNC_0h", "shTDG_0h")
    # Correlation
    r, _ = stats.pearsonr(fig4c[:,2], fig4c[:,4])
    print(f"\nshHDAC6_0h vs shTET2_0h correlation: r = {r:.4f}")
    # Benford
    vals = np.concatenate([fig4c.flatten(), fig4f.flatten()])
    fd = [int(f"{abs(v):.10f}".lstrip('0.')[0]) for v in vals if v != 0]
    fd = [d for d in fd if 1 <= d <= 9]
    N = len(fd)
    counts = Counter(fd)
    chi2 = sum(N*(counts.get(d,0)/N - np.log10(1+1/d))**2/np.log10(1+1/d) for d in range(1,10))
    print(f"\nBenford chi2 = {chi2:.1f}, N = {N}")
    print("\nDone. See forensic_report.md for full analysis.")

if __name__ == '__main__':
    main()
