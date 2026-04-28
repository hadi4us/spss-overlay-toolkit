#!/usr/bin/env python3
"""
Overlay / merge data file (terutama .sav SPSS) dengan opsi prioritas kolom.

Contoh:
  python overlay_sav.py \
    --base data/base.sav \
    --overlay data/patch.sav \
    --keys id \
    --how left \
    --method replace \
    --output out/hasil.sav \
    --report out/report.json
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Iterable


def _require(name: str):
    try:
        return __import__(name)
    except ImportError as e:
        raise SystemExit(
            f"Dependency '{name}' belum terpasang. Jalankan: pip install -r requirements-python.txt"
        ) from e


pd = _require("pandas")
pyreadstat = _require("pyreadstat")


@dataclass
class IOResult:
    df: "pd.DataFrame"
    source_type: str


def parse_csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def read_table(path: str) -> IOResult:
    ex = ext(path)
    if ex == ".sav":
        df, _meta = pyreadstat.read_sav(path)
        return IOResult(df=df, source_type="sav")
    if ex == ".csv":
        return IOResult(df=pd.read_csv(path), source_type="csv")
    if ex in {".xlsx", ".xls"}:
        return IOResult(df=pd.read_excel(path), source_type="excel")
    if ex == ".parquet":
        return IOResult(df=pd.read_parquet(path), source_type="parquet")
    raise SystemExit(f"Format input tidak didukung: {path}")


def write_table(df: "pd.DataFrame", path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ex = ext(path)
    if ex == ".sav":
        pyreadstat.write_sav(df, path)
        return
    if ex == ".csv":
        df.to_csv(path, index=False)
        return
    if ex in {".xlsx", ".xls"}:
        df.to_excel(path, index=False)
        return
    if ex == ".parquet":
        df.to_parquet(path, index=False)
        return
    raise SystemExit(f"Format output tidak didukung: {path}")


def normalize_columns(df: "pd.DataFrame") -> "pd.DataFrame":
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out


def ensure_keys(df: "pd.DataFrame", keys: Iterable[str], label: str) -> None:
    missing = [k for k in keys if k not in df.columns]
    if missing:
        raise SystemExit(f"Kolom key tidak ditemukan di {label}: {missing}")


def _normalize_key_value(x):
    if pd.isna(x):
        return pd.NA

    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none", "<na>"}:
        return pd.NA

    # Jika string angka berakhiran .0 (mis. 92.0), ubah jadi 92
    if s.replace(".", "", 1).isdigit() and s.endswith(".0"):
        try:
            f = float(s)
            if f.is_integer():
                return str(int(f))
        except Exception:
            pass

    return s


def normalize_key_columns(df: "pd.DataFrame", keys: list[str]) -> "pd.DataFrame":
    out = df.copy()
    for k in keys:
        if k in out.columns:
            out[k] = out[k].map(_normalize_key_value)
    return out


def overlay_merge(
    base_df: "pd.DataFrame",
    overlay_df: "pd.DataFrame",
    keys: list[str],
    how: str,
    method: str,
    include_cols: list[str],
    exclude_cols: list[str],
    clean_keys: bool = False,
) -> tuple["pd.DataFrame", dict]:
    if clean_keys:
        base_df = normalize_key_columns(base_df, keys)
        overlay_df = normalize_key_columns(overlay_df, keys)

    base_non_keys = [c for c in base_df.columns if c not in keys]

    if include_cols:
        overlay_cols = [c for c in include_cols if c in overlay_df.columns and c not in keys]
    else:
        overlay_cols = [c for c in overlay_df.columns if c not in keys]

    if exclude_cols:
        overlay_cols = [c for c in overlay_cols if c not in set(exclude_cols)]

    if not overlay_cols:
        raise SystemExit("Tidak ada kolom overlay yang dipilih. Cek include/exclude.")

    # Hindari duplikasi key di sisi overlay (ambil data terakhir)
    overlay_uniq = overlay_df[keys + overlay_cols].drop_duplicates(subset=keys, keep="last")

    merged = base_df.merge(
        overlay_uniq,
        on=keys,
        how=how,
        suffixes=("_base", "_ovr"),
        indicator=True,
    )

    overlap_cols = [c for c in overlay_cols if c in base_non_keys]

    for col in overlap_cols:
        c_base = f"{col}_base"
        c_ovr = f"{col}_ovr"
        if method == "coalesce":
            merged[col] = merged[c_base].combine_first(merged[c_ovr])
        elif method == "replace":
            merged[col] = merged[c_ovr].combine_first(merged[c_base])
        elif method == "keep_base":
            merged[col] = merged[c_base]
        elif method == "keep_overlay":
            merged[col] = merged[c_ovr]
        else:
            raise SystemExit(f"Method tidak dikenal: {method}")

    # Rapikan kolom non-overlap yang masih bersufiks
    rename_back = {}
    for c in merged.columns:
        if c.endswith("_base"):
            base_name = c[:-5]
            if base_name not in overlap_cols:
                rename_back[c] = base_name
        if c.endswith("_ovr"):
            ovr_name = c[:-4]
            if ovr_name not in overlap_cols and ovr_name not in base_df.columns:
                rename_back[c] = ovr_name

    merged = merged.rename(columns=rename_back)

    drop_cols = [f"{c}_base" for c in overlap_cols] + [f"{c}_ovr" for c in overlap_cols]
    merged = merged.drop(columns=[c for c in drop_cols if c in merged.columns])

    merge_counts = merged["_merge"].value_counts(dropna=False).to_dict()
    report = {
        "base_rows": int(len(base_df)),
        "overlay_rows": int(len(overlay_df)),
        "overlay_rows_after_dedup": int(len(overlay_uniq)),
        "output_rows": int(len(merged)),
        "merge_counts": {k: int(v) for k, v in merge_counts.items()},
        "keys": keys,
        "how": how,
        "method": method,
        "clean_keys": bool(clean_keys),
        "overlay_columns_used": overlay_cols,
        "overlap_columns": overlap_cols,
    }

    merged = merged.drop(columns=["_merge"])
    return merged, report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Overlay/merge file .sav/.csv/.xlsx/.parquet")
    p.add_argument("--base", required=True, help="File base (mis. data_awal.sav)")
    p.add_argument("--overlay", required=True, help="File overlay/patch")
    p.add_argument("--keys", required=True, help="Kolom key, pisahkan koma. Contoh: id atau id,tanggal")
    p.add_argument("--output", required=True, help="Output file (.sav/.csv/.xlsx/.parquet)")
    p.add_argument("--report", help="Path JSON report ringkas")
    p.add_argument("--how", default="left", choices=["left", "inner", "right", "outer"])
    p.add_argument(
        "--method",
        default="coalesce",
        choices=["coalesce", "replace", "keep_base", "keep_overlay"],
        help=(
            "Strategi untuk kolom nama sama. "
            "coalesce=base dulu, replace=overlay dulu, keep_base=tetap base, keep_overlay=pakai overlay"
        ),
    )
    p.add_argument("--include-cols", help="Kolom overlay yang dipakai (koma). Default: semua")
    p.add_argument("--exclude-cols", help="Kolom overlay yang dibuang (koma)")
    p.add_argument(
        "--normalize-cols",
        action="store_true",
        help="Normalisasi nama kolom jadi lowercase + underscore",
    )
    p.add_argument(
        "--clean-keys",
        action="store_true",
        help="Bersihkan nilai key sebelum merge (trim spasi, rapikan angka seperti 92.0 -> 92)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    keys = parse_csv_list(args.keys)
    include_cols = parse_csv_list(args.include_cols)
    exclude_cols = parse_csv_list(args.exclude_cols)

    if not keys:
        raise SystemExit("--keys wajib diisi")

    base_in = read_table(args.base)
    ovr_in = read_table(args.overlay)

    base_df = base_in.df
    overlay_df = ovr_in.df

    if args.normalize_cols:
        base_df = normalize_columns(base_df)
        overlay_df = normalize_columns(overlay_df)
        keys = [k.strip().lower().replace(" ", "_") for k in keys]
        include_cols = [c.strip().lower().replace(" ", "_") for c in include_cols]
        exclude_cols = [c.strip().lower().replace(" ", "_") for c in exclude_cols]

    ensure_keys(base_df, keys, "base")
    ensure_keys(overlay_df, keys, "overlay")

    result_df, report = overlay_merge(
        base_df=base_df,
        overlay_df=overlay_df,
        keys=keys,
        how=args.how,
        method=args.method,
        include_cols=include_cols,
        exclude_cols=exclude_cols,
        clean_keys=args.clean_keys,
    )

    write_table(result_df, args.output)

    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    print("[OK] Overlay selesai")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
