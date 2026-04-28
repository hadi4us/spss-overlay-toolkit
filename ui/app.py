#!/usr/bin/env python3
from __future__ import annotations

import hmac
import json
import os
import sys
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from overlay_sav import normalize_columns, overlay_merge  # noqa: E402

try:
    import pyreadstat
except ImportError:  # pragma: no cover
    pyreadstat = None

try:
    from scipy import stats
except ImportError:  # pragma: no cover
    stats = None

try:
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
except ImportError:  # pragma: no cover
    sm = None
    smf = None

APP_TITLE = "SPSS-Like Data Studio"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))


def ensure_state() -> None:
    defaults: dict[str, Any] = {
        "df": None,
        "dataset_name": None,
        "overlay_base_df": None,
        "overlay_patch_df": None,
        "overlay_report": None,
        "overlay_result_df": None,
        "overlay_multi_data": None,
        "transform_logs": [],
        "inferential_logs": [],
        "last_quality_report": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def _append_log(kind: str, title: str, payload: dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "kind": kind,
        "title": title,
        "payload": payload,
    }
    if kind == "transform":
        st.session_state.transform_logs = [entry] + st.session_state.transform_logs[:99]
    elif kind == "inferential":
        st.session_state.inferential_logs = [entry] + st.session_state.inferential_logs[:99]


def _check_upload_limit(uploaded_file) -> None:
    size = getattr(uploaded_file, "size", None)
    if size is None:
        return
    if size > MAX_UPLOAD_MB * 1024 * 1024:
        raise RuntimeError(
            f"Ukuran file {size / (1024 * 1024):.1f} MB melebihi batas {MAX_UPLOAD_MB} MB."
        )


def _auth_gate() -> bool:
    required_user = os.getenv("UI_USERNAME")
    required_pass = os.getenv("UI_PASSWORD")

    if not required_user and not required_pass:
        return True

    if st.session_state.get("auth_ok"):
        return True

    st.warning("Aplikasi ini diproteksi login.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")

    if submit:
        user_ok = True if not required_user else hmac.compare_digest(username or "", required_user)
        pass_ok = True if not required_pass else hmac.compare_digest(password or "", required_pass)
        if user_ok and pass_ok:
            st.session_state.auth_ok = True
            st.success("Login berhasil. Silakan lanjut.")
            st.rerun()
        else:
            st.error("Username/password salah.")

    return False


def _read_uploaded(uploaded_file) -> pd.DataFrame:
    _check_upload_limit(uploaded_file)
    ext = _ext(uploaded_file.name)
    if ext == ".csv":
        return pd.read_csv(uploaded_file)
    if ext in {".xlsx", ".xls"}:
        return pd.read_excel(uploaded_file)
    if ext == ".parquet":
        return pd.read_parquet(uploaded_file)
    if ext == ".sav":
        if pyreadstat is None:
            raise RuntimeError("pyreadstat belum terpasang. Jalankan: pip install -r requirements-ui.txt")
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name
        try:
            df, _ = pyreadstat.read_sav(tmp_path)
            return df
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    raise ValueError(f"Format tidak didukung: {uploaded_file.name}")


def _df_to_download(df: pd.DataFrame, fmt: str) -> tuple[bytes, str, str]:
    fmt = fmt.lower()
    if fmt == "csv":
        return df.to_csv(index=False).encode("utf-8"), "text/csv", "csv"

    if fmt == "xlsx":
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="data")
        return bio.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"

    if fmt == "parquet":
        bio = BytesIO()
        df.to_parquet(bio, index=False)
        return bio.getvalue(), "application/octet-stream", "parquet"

    if fmt == "sav":
        if pyreadstat is None:
            raise RuntimeError("pyreadstat belum terpasang. Tidak bisa export SAV.")
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            pyreadstat.write_sav(df, tmp_path)
            with open(tmp_path, "rb") as f:
                return f.read(), "application/octet-stream", "sav"
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    raise ValueError(f"Format export tidak didukung: {fmt}")


def _variable_view(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    n = len(df)
    for c in df.columns:
        s = df[c]
        missing = int(s.isna().sum())
        rows.append(
            {
                "variable": c,
                "dtype": str(s.dtype),
                "missing_n": missing,
                "missing_pct": round((missing / n * 100), 3) if n else 0,
                "unique_n": int(s.nunique(dropna=True)),
                "example": str(s.dropna().iloc[0]) if s.notna().any() else None,
            }
        )
    return pd.DataFrame(rows)


def _page_dataset() -> None:
    st.subheader("Dataset Manager")
    st.caption("Upload file .sav/.csv/.xlsx/.parquet untuk jadi dataset aktif.")

    up = st.file_uploader(
        "Upload dataset",
        type=["sav", "csv", "xlsx", "xls", "parquet"],
        key="dataset_uploader",
    )

    if up is not None:
        try:
            df = _read_uploaded(up)
            st.session_state.df = df
            st.session_state.dataset_name = up.name
            st.success(f"Dataset aktif: {up.name} ({len(df):,} baris, {len(df.columns):,} kolom)")
        except Exception as e:
            st.error(str(e))

    df = st.session_state.df
    if df is not None:
        col1, col2, col3 = st.columns(3)
        col1.metric("Rows", f"{len(df):,}")
        col2.metric("Columns", f"{len(df.columns):,}")
        mem_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
        col3.metric("Memory", f"{mem_mb:.2f} MB")

        st.markdown("**Preview (100 baris pertama)**")
        st.dataframe(df.head(100), use_container_width=True)


def _require_df() -> pd.DataFrame | None:
    df = st.session_state.df
    if df is None:
        st.info("Belum ada dataset aktif. Buka menu **Dataset** dulu.")
        return None
    return df


def _common_columns(dfs: list[pd.DataFrame]) -> list[str]:
    if not dfs:
        return []
    common = set(dfs[0].columns)
    for df in dfs[1:]:
        common &= set(df.columns)
    return sorted(common)


def _page_variable_view() -> None:
    st.subheader("Variable View")
    df = _require_df()
    if df is None:
        return

    var_df = _variable_view(df)
    st.dataframe(var_df, use_container_width=True)


def _page_descriptive() -> None:
    st.subheader("Descriptive Statistics")
    df = _require_df()
    if df is None:
        return

    num_cols = list(df.select_dtypes(include="number").columns)
    if not num_cols:
        st.warning("Tidak ada kolom numerik.")
        return

    selected = st.multiselect("Pilih kolom numerik", options=num_cols, default=num_cols[: min(10, len(num_cols))])
    if not selected:
        st.info("Pilih minimal 1 kolom.")
        return

    desc = df[selected].describe(percentiles=[0.25, 0.5, 0.75]).T
    desc["missing_n"] = df[selected].isna().sum()
    desc["missing_pct"] = (desc["missing_n"] / len(df) * 100).round(3)
    st.dataframe(desc, use_container_width=True)


def _page_frequency() -> None:
    st.subheader("Frequencies")
    df = _require_df()
    if df is None:
        return

    col = st.selectbox("Pilih variabel", options=list(df.columns))
    top_n = st.slider("Top N kategori", 5, 100, 20)
    show_na = st.checkbox("Sertakan missing (NA)", value=True)

    vc = df[col].value_counts(dropna=not show_na).head(top_n)
    freq_df = vc.rename_axis(col).reset_index(name="count")
    freq_df["percent"] = (freq_df["count"] / len(df) * 100).round(3)
    st.dataframe(freq_df, use_container_width=True)

    fig = px.bar(freq_df, x=col, y="count", title=f"Frekuensi: {col}")
    st.plotly_chart(fig, use_container_width=True)


def _page_crosstab() -> None:
    st.subheader("Crosstabs")
    df = _require_df()
    if df is None:
        return

    cols = list(df.columns)
    c1, c2 = st.columns(2)
    row = c1.selectbox("Row variable", options=cols, key="ct_row")
    col = c2.selectbox("Column variable", options=cols, key="ct_col")
    norm = st.selectbox("Normalize", options=["none", "index", "columns", "all"], index=0)

    normalize = None if norm == "none" else norm
    ct = pd.crosstab(df[row], df[col], normalize=normalize, dropna=False)
    st.dataframe(ct, use_container_width=True)


def _page_correlation() -> None:
    st.subheader("Correlation Matrix")
    df = _require_df()
    if df is None:
        return

    num_cols = list(df.select_dtypes(include="number").columns)
    if len(num_cols) < 2:
        st.warning("Perlu minimal 2 kolom numerik.")
        return

    selected = st.multiselect("Kolom numerik", options=num_cols, default=num_cols[: min(10, len(num_cols))])
    method = st.selectbox("Method", options=["pearson", "spearman", "kendall"], index=0)

    if len(selected) < 2:
        st.info("Pilih minimal 2 kolom.")
        return

    corr = df[selected].corr(method=method)
    st.dataframe(corr, use_container_width=True)

    fig = px.imshow(
        corr,
        text_auto=True,
        color_continuous_scale="RdBu",
        zmin=-1,
        zmax=1,
        title=f"Correlation ({method})",
    )
    st.plotly_chart(fig, use_container_width=True)


def _page_charts() -> None:
    st.subheader("Charts")
    df = _require_df()
    if df is None:
        return

    chart_type = st.selectbox("Tipe chart", options=["Histogram", "Scatter", "Box", "Line", "Bar"])
    cols = list(df.columns)

    if chart_type == "Histogram":
        x = st.selectbox("X", options=cols, key="hist_x")
        bins = st.slider("Bins", 5, 100, 30)
        fig = px.histogram(df, x=x, nbins=bins)
        st.plotly_chart(fig, use_container_width=True)

    elif chart_type == "Scatter":
        num_cols = list(df.select_dtypes(include="number").columns)
        if len(num_cols) < 2:
            st.warning("Perlu minimal 2 kolom numerik.")
            return
        x = st.selectbox("X", options=num_cols, key="scatter_x")
        y = st.selectbox("Y", options=[c for c in num_cols if c != x], key="scatter_y")
        color = st.selectbox("Color (opsional)", options=[None] + cols, index=0)
        fig = px.scatter(df, x=x, y=y, color=color)
        st.plotly_chart(fig, use_container_width=True)

    elif chart_type == "Box":
        num_cols = list(df.select_dtypes(include="number").columns)
        if not num_cols:
            st.warning("Tidak ada kolom numerik.")
            return
        y = st.selectbox("Y (numeric)", options=num_cols, key="box_y")
        x = st.selectbox("X (grouping, opsional)", options=[None] + cols, index=0, key="box_x")
        fig = px.box(df, x=x, y=y)
        st.plotly_chart(fig, use_container_width=True)

    elif chart_type == "Line":
        x = st.selectbox("X", options=cols, key="line_x")
        y = st.selectbox("Y", options=cols, key="line_y")
        fig = px.line(df, x=x, y=y)
        st.plotly_chart(fig, use_container_width=True)

    elif chart_type == "Bar":
        x = st.selectbox("X", options=cols, key="bar_x")
        y = st.selectbox("Y (opsional)", options=[None] + cols, index=0, key="bar_y")
        if y is None:
            bar_df = df[x].value_counts().reset_index()
            bar_df.columns = [x, "count"]
            fig = px.bar(bar_df, x=x, y="count")
        else:
            agg = st.selectbox("Agregasi Y", options=["sum", "mean", "median", "min", "max"], index=1)
            bar_df = df.groupby(x, dropna=False)[y].agg(agg).reset_index()
            fig = px.bar(bar_df, x=x, y=y)
        st.plotly_chart(fig, use_container_width=True)


def _run_data_quality(df: pd.DataFrame, key_cols: list[str] | None = None) -> dict[str, Any]:
    key_cols = key_cols or []
    report: dict[str, Any] = {}

    rows, cols = df.shape
    report["shape"] = {"rows": int(rows), "columns": int(cols)}

    missing = df.isna().sum().sort_values(ascending=False)
    missing_df = pd.DataFrame({
        "column": missing.index,
        "missing_n": missing.values,
        "missing_pct": ((missing.values / max(rows, 1)) * 100).round(3),
    })
    report["missing_table"] = missing_df

    dtypes_df = pd.DataFrame(
        {
            "column": df.columns,
            "dtype": [str(df[c].dtype) for c in df.columns],
            "unique_n": [int(df[c].nunique(dropna=True)) for c in df.columns],
        }
    )
    report["dtypes_table"] = dtypes_df

    numeric_cols = list(df.select_dtypes(include="number").columns)
    outlier_rows = []
    for c in numeric_cols:
        s = df[c].dropna()
        if len(s) < 5:
            outlier_rows.append({"column": c, "outlier_n": 0, "outlier_pct": 0.0})
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            out_n = 0
        else:
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            out_n = int(((s < low) | (s > high)).sum())
        outlier_rows.append(
            {
                "column": c,
                "outlier_n": out_n,
                "outlier_pct": round((out_n / max(len(s), 1)) * 100, 3),
            }
        )
    report["outlier_table"] = pd.DataFrame(outlier_rows)

    if key_cols:
        missing_keys = [k for k in key_cols if k not in df.columns]
        if missing_keys:
            report["key_check"] = {"ok": False, "error": f"Key tidak ditemukan: {missing_keys}"}
        else:
            dup_n = int(df.duplicated(subset=key_cols, keep=False).sum())
            report["key_check"] = {
                "ok": dup_n == 0,
                "duplicate_rows": dup_n,
                "keys": key_cols,
            }
    else:
        report["key_check"] = {"ok": None, "note": "Belum pilih key."}

    score = 100.0
    max_missing = float(missing_df["missing_pct"].max()) if len(missing_df) else 0.0
    score -= min(40.0, max_missing * 0.4)
    dup_penalty = 0.0
    if report["key_check"].get("duplicate_rows"):
        dup_penalty = min(30.0, report["key_check"]["duplicate_rows"] / max(rows, 1) * 100)
        score -= dup_penalty
    outlier_total = int(report["outlier_table"]["outlier_n"].sum()) if len(report["outlier_table"]) else 0
    outlier_penalty = min(20.0, (outlier_total / max(rows, 1)) * 100)
    score -= outlier_penalty
    score = round(max(score, 0), 2)

    report["score"] = {
        "data_quality_score": score,
        "max_missing_pct": round(max_missing, 3),
        "dup_penalty": round(dup_penalty, 3),
        "outlier_penalty": round(outlier_penalty, 3),
    }

    return report


def _page_quality() -> None:
    st.subheader("Data Quality Center")
    df = _require_df()
    if df is None:
        return

    key_options = list(df.columns)
    selected_keys = st.multiselect("Pilih key untuk cek duplicate", options=key_options, default=[])

    if st.button("Run Data Quality Check", type="primary"):
        report = _run_data_quality(df, key_cols=selected_keys)
        st.session_state.last_quality_report = report

    report = st.session_state.last_quality_report
    if report:
        sc = report["score"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Quality Score", f"{sc['data_quality_score']}")
        c2.metric("Max Missing %", f"{sc['max_missing_pct']}%")
        c3.metric("Duplicate Rows (key)", report["key_check"].get("duplicate_rows", 0))

        st.markdown("### Missingness")
        st.dataframe(report["missing_table"], use_container_width=True)

        st.markdown("### Type & Cardinality")
        st.dataframe(report["dtypes_table"], use_container_width=True)

        st.markdown("### Outlier Ringkas (IQR)")
        st.dataframe(report["outlier_table"], use_container_width=True)

    st.markdown("---")
    st.markdown("### Schema Compare (opsional)")
    cmp_file = st.file_uploader(
        "Upload dataset pembanding untuk cek schema mismatch",
        type=["sav", "csv", "xlsx", "xls", "parquet"],
        key="quality_compare_uploader",
    )
    if cmp_file is not None:
        try:
            cmp_df = _read_uploaded(cmp_file)
            left_only = sorted(list(set(df.columns) - set(cmp_df.columns)))
            right_only = sorted(list(set(cmp_df.columns) - set(df.columns)))
            common = sorted(list(set(df.columns).intersection(set(cmp_df.columns))))
            mismatch = []
            for col in common:
                t1 = str(df[col].dtype)
                t2 = str(cmp_df[col].dtype)
                if t1 != t2:
                    mismatch.append({"column": col, "active_dtype": t1, "compare_dtype": t2})

            c1, c2, c3 = st.columns(3)
            c1.metric("Columns only in active", len(left_only))
            c2.metric("Columns only in compare", len(right_only))
            c3.metric("Type mismatches", len(mismatch))

            if left_only:
                st.write("Only in active:", left_only)
            if right_only:
                st.write("Only in compare:", right_only)
            if mismatch:
                st.dataframe(pd.DataFrame(mismatch), use_container_width=True)
            else:
                st.success("Tidak ada mismatch tipe untuk kolom yang sama.")
        except Exception as e:
            st.error(str(e))


def _set_active_df(df: pd.DataFrame, name: str, log_title: str, log_payload: dict[str, Any]) -> None:
    st.session_state.df = df
    st.session_state.dataset_name = name
    _append_log("transform", log_title, log_payload)


def _page_transform() -> None:
    st.subheader("Transform & Data Prep")
    df = _require_df()
    if df is None:
        return

    tab_recode, tab_compute, tab_binning, tab_missing, tab_filter, tab_logs = st.tabs(
        ["Recode", "Compute", "Binning", "Missing", "Filter", "Transform Logs"]
    )

    with tab_recode:
        col = st.selectbox("Kolom yang direcode", options=list(df.columns), key="recode_col")
        mode = st.radio("Mode", ["Manual mapping", "Kategori ke kategori"], horizontal=True)
        target = st.text_input("Nama kolom output (kosongkan untuk overwrite)", value="", key="recode_target")

        if mode == "Manual mapping":
            raw_map = st.text_area(
                "Mapping (1 baris per aturan: nilai_lama=nilai_baru)",
                value="",
                height=120,
                key="recode_map",
            )
            if st.button("Apply Recode", key="btn_recode"):
                mapping: dict[Any, Any] = {}
                for line in raw_map.splitlines():
                    if not line.strip() or "=" not in line:
                        continue
                    a, b = line.split("=", 1)
                    mapping[a.strip()] = b.strip()
                out_col = target.strip() or col
                new_df = df.copy()
                new_df[out_col] = new_df[col].astype(str).replace(mapping)
                _set_active_df(
                    new_df,
                    f"{st.session_state.dataset_name}_recode",
                    "Recode variable",
                    {"column": col, "output_column": out_col, "mapping_size": len(mapping)},
                )
                st.success(f"Recode selesai: {col} -> {out_col}")
        else:
            st.info("Untuk mode kategori, gunakan format mapping yang sama (old=new).")

    with tab_compute:
        numeric_cols = list(df.select_dtypes(include="number").columns)
        st.caption("Contoh formula: (pendapatan - biaya) / biaya")
        formula = st.text_input("Formula (pakai nama kolom)", value="", key="compute_formula")
        new_col = st.text_input("Nama kolom hasil", value="var_baru", key="compute_out")
        if numeric_cols:
            st.write("Kolom numerik tersedia:", numeric_cols)
        if st.button("Apply Compute", key="btn_compute"):
            if not formula.strip() or not new_col.strip():
                st.error("Formula dan nama kolom wajib diisi.")
            else:
                try:
                    new_df = df.copy()
                    new_df[new_col.strip()] = new_df.eval(formula)
                    _set_active_df(
                        new_df,
                        f"{st.session_state.dataset_name}_compute",
                        "Compute variable",
                        {"formula": formula, "output_column": new_col.strip()},
                    )
                    st.success(f"Compute selesai: {new_col}")
                except Exception as e:
                    st.error(f"Compute gagal: {e}")

    with tab_binning:
        num_cols = list(df.select_dtypes(include="number").columns)
        if not num_cols:
            st.info("Tidak ada kolom numerik untuk binning.")
        else:
            src = st.selectbox("Kolom numerik", options=num_cols, key="bin_col")
            bins = st.slider("Jumlah bin", 2, 20, 5, key="bin_n")
            out_col = st.text_input("Nama kolom bin", value=f"{src}_bin", key="bin_out")
            if st.button("Apply Binning", key="btn_bin"):
                try:
                    new_df = df.copy()
                    new_df[out_col] = pd.cut(new_df[src], bins=bins, include_lowest=True).astype(str)
                    _set_active_df(
                        new_df,
                        f"{st.session_state.dataset_name}_binning",
                        "Binning",
                        {"column": src, "bins": bins, "output_column": out_col},
                    )
                    st.success(f"Binning selesai: {out_col}")
                except Exception as e:
                    st.error(str(e))

    with tab_missing:
        col = st.selectbox("Kolom", options=list(df.columns), key="mis_col")
        method = st.selectbox("Metode imputasi", options=["mean", "median", "mode", "constant"], key="mis_method")
        const_val = st.text_input("Nilai constant (jika method=constant)", value="", key="mis_const")
        if st.button("Apply Missing Handler", key="btn_missing"):
            new_df = df.copy()
            try:
                if method == "mean":
                    fillv = new_df[col].mean()
                elif method == "median":
                    fillv = new_df[col].median()
                elif method == "mode":
                    fillv = new_df[col].mode(dropna=True)
                    fillv = fillv.iloc[0] if len(fillv) else None
                else:
                    fillv = const_val
                new_df[col] = new_df[col].fillna(fillv)
                _set_active_df(
                    new_df,
                    f"{st.session_state.dataset_name}_missing",
                    "Handle missing",
                    {"column": col, "method": method, "fill_value": str(fillv)},
                )
                st.success(f"Missing handler selesai untuk {col}")
            except Exception as e:
                st.error(str(e))

    with tab_filter:
        st.caption("Contoh query: usia >= 18 and status == 'AKTIF'")
        q = st.text_input("Filter query (pandas.query)", value="", key="filter_query")
        if st.button("Apply Filter", key="btn_filter"):
            try:
                new_df = df.query(q).copy() if q.strip() else df.copy()
                _set_active_df(
                    new_df,
                    f"{st.session_state.dataset_name}_filter",
                    "Filter cases",
                    {"query": q, "rows_after": int(len(new_df))},
                )
                st.success(f"Filter selesai. Baris sekarang: {len(new_df):,}")
            except Exception as e:
                st.error(str(e))

    with tab_logs:
        logs = st.session_state.transform_logs
        if not logs:
            st.info("Belum ada transform log.")
        else:
            st.dataframe(pd.DataFrame(logs), use_container_width=True)


def _fmt_p(p: float) -> str:
    if p < 0.0001:
        return "< 0.0001"
    return f"{p:.4f}"


def _build_formula(y: str, x_cols: list[str], data: pd.DataFrame) -> str:
    parts = []
    for x in x_cols:
        if str(data[x].dtype) in {"object", "category", "bool"}:
            parts.append(f"C(Q('{x}'))")
        else:
            parts.append(f"Q('{x}')")
    rhs = " + ".join(parts) if parts else "1"
    return f"Q('{y}') ~ {rhs}"


def _page_inferential() -> None:
    st.subheader("Inferential Statistics")
    df = _require_df()
    if df is None:
        return

    if stats is None or sm is None or smf is None:
        st.error("Paket inferensial belum terpasang. Jalankan ulang run_ui.sh untuk install scipy/statsmodels.")
        return

    t_t, t_chi, t_anova, t_lin, t_logit, t_logs = st.tabs(
        ["T-Test", "Chi-Square", "ANOVA", "Linear Reg", "Logistic Reg", "Inferential Logs"]
    )

    with t_t:
        num_cols = list(df.select_dtypes(include="number").columns)
        cat_cols = list(df.columns)
        if not num_cols:
            st.info("Tidak ada kolom numerik untuk t-test.")
        else:
            y = st.selectbox("Variable numerik", options=num_cols, key="tt_y")
            g = st.selectbox("Grouping variable", options=cat_cols, key="tt_g")
            groups = [x for x in df[g].dropna().unique().tolist()]
            if len(groups) < 2:
                st.warning("Grouping variable harus punya minimal 2 kategori.")
            else:
                g1 = st.selectbox("Group 1", options=groups, index=0, key="tt_g1")
                g2 = st.selectbox("Group 2", options=groups, index=1 if len(groups) > 1 else 0, key="tt_g2")
                equal_var = st.checkbox("Assume equal variance", value=False, key="tt_eq")
                if st.button("Run T-Test", key="btn_ttest"):
                    s1 = df.loc[df[g] == g1, y].dropna()
                    s2 = df.loc[df[g] == g2, y].dropna()
                    if len(s1) < 2 or len(s2) < 2:
                        st.error("Masing-masing group minimal 2 observasi.")
                    else:
                        tstat, pval = stats.ttest_ind(s1, s2, equal_var=equal_var)
                        res = {
                            "test": "independent_ttest",
                            "y": y,
                            "group_var": g,
                            "group1": str(g1),
                            "group2": str(g2),
                            "n1": int(len(s1)),
                            "n2": int(len(s2)),
                            "mean1": float(s1.mean()),
                            "mean2": float(s2.mean()),
                            "t_stat": float(tstat),
                            "p_value": float(pval),
                            "interpretasi": "Signifikan" if pval < 0.05 else "Tidak signifikan",
                        }
                        st.json(res)
                        _append_log("inferential", "T-Test", res)

    with t_chi:
        cols = list(df.columns)
        r = st.selectbox("Row variable", options=cols, key="chi_r")
        c = st.selectbox("Column variable", options=cols, key="chi_c")
        if st.button("Run Chi-Square", key="btn_chi"):
            tab = pd.crosstab(df[r], df[c], dropna=False)
            if tab.shape[0] < 2 or tab.shape[1] < 2:
                st.error("Crosstab harus minimal 2x2.")
            else:
                chi2, pval, dof, expected = stats.chi2_contingency(tab)
                res = {
                    "test": "chi_square",
                    "row": r,
                    "column": c,
                    "chi2": float(chi2),
                    "dof": int(dof),
                    "p_value": float(pval),
                    "interpretasi": "Ada asosiasi" if pval < 0.05 else "Tidak ada asosiasi signifikan",
                }
                st.dataframe(tab, use_container_width=True)
                st.json(res)
                _append_log("inferential", "Chi-Square", res)

    with t_anova:
        num_cols = list(df.select_dtypes(include="number").columns)
        cols = list(df.columns)
        if not num_cols:
            st.info("Tidak ada kolom numerik untuk ANOVA.")
        else:
            y = st.selectbox("Dependent variable (numeric)", options=num_cols, key="anova_y")
            x = st.selectbox("Factor", options=cols, key="anova_x")
            if st.button("Run One-way ANOVA", key="btn_anova"):
                d = df[[y, x]].dropna().copy()
                if d[x].nunique() < 2:
                    st.error("Factor harus punya minimal 2 kategori.")
                else:
                    model = smf.ols(f"Q('{y}') ~ C(Q('{x}'))", data=d).fit()
                    anova_tbl = sm.stats.anova_lm(model, typ=2)
                    pval = float(anova_tbl["PR(>F)"].iloc[0])
                    st.dataframe(anova_tbl, use_container_width=True)
                    res = {
                        "test": "anova_one_way",
                        "y": y,
                        "x": x,
                        "p_value": pval,
                        "interpretasi": "Ada perbedaan mean antar grup" if pval < 0.05 else "Tidak ada perbedaan mean signifikan",
                    }
                    st.json(res)
                    _append_log("inferential", "ANOVA", res)

    with t_lin:
        num_cols = list(df.select_dtypes(include="number").columns)
        all_cols = list(df.columns)
        if len(num_cols) < 1:
            st.info("Tidak ada kolom numerik untuk regresi linear.")
        else:
            y = st.selectbox("Y (dependent numeric)", options=num_cols, key="lin_y")
            x_cols = st.multiselect("X variables", options=[c for c in all_cols if c != y], key="lin_x")
            if st.button("Run Linear Regression", key="btn_lin"):
                if not x_cols:
                    st.error("Pilih minimal 1 variabel X.")
                else:
                    d = df[[y] + x_cols].dropna().copy()
                    formula = _build_formula(y, x_cols, d)
                    model = smf.ols(formula, data=d).fit()
                    coef = model.summary2().tables[1].reset_index().rename(columns={"index": "term"})
                    st.dataframe(coef, use_container_width=True)
                    res = {
                        "test": "linear_regression",
                        "formula": formula,
                        "n_obs": int(model.nobs),
                        "r_squared": float(model.rsquared),
                        "adj_r_squared": float(model.rsquared_adj),
                        "f_pvalue": float(model.f_pvalue),
                        "interpretasi": "Model signifikan" if model.f_pvalue < 0.05 else "Model belum signifikan",
                    }
                    st.json(res)
                    _append_log("inferential", "Linear Regression", res)

    with t_logit:
        cols = list(df.columns)
        y = st.selectbox("Y (binary)", options=cols, key="logit_y")
        x_cols = st.multiselect("X variables", options=[c for c in cols if c != y], key="logit_x")
        if st.button("Run Logistic Regression", key="btn_logit"):
            if not x_cols:
                st.error("Pilih minimal 1 variabel X.")
            else:
                d = df[[y] + x_cols].dropna().copy()
                y_unique = d[y].dropna().unique().tolist()
                if len(y_unique) != 2:
                    st.error("Y harus binary (2 kategori/angka).")
                else:
                    mapping = {y_unique[0]: 0, y_unique[1]: 1}
                    d[y] = d[y].map(mapping)
                    formula = _build_formula(y, x_cols, d)
                    try:
                        model = smf.logit(formula, data=d).fit(disp=False)
                        coef = model.summary2().tables[1].reset_index().rename(columns={"index": "term"})
                        st.dataframe(coef, use_container_width=True)
                        res = {
                            "test": "logistic_regression",
                            "formula": formula,
                            "n_obs": int(model.nobs),
                            "pseudo_r2": float(getattr(model, "prsquared", np.nan)),
                            "llr_pvalue": float(getattr(model, "llr_pvalue", np.nan)),
                            "mapping_y": {str(k): int(v) for k, v in mapping.items()},
                            "interpretasi": "Model signifikan" if float(getattr(model, "llr_pvalue", 1.0)) < 0.05 else "Model belum signifikan",
                        }
                        st.json(res)
                        _append_log("inferential", "Logistic Regression", res)
                    except Exception as e:
                        st.error(f"Logistic regression gagal: {e}")

    with t_logs:
        logs = st.session_state.inferential_logs
        if not logs:
            st.info("Belum ada inferential log.")
        else:
            st.dataframe(pd.DataFrame(logs), use_container_width=True)


def _page_report() -> None:
    st.subheader("Report Generator")
    df = _require_df()
    if df is None:
        return

    include_quality = st.checkbox("Include data quality summary", value=True)
    include_transform = st.checkbox("Include transform logs", value=True)
    include_inferential = st.checkbox("Include inferential logs", value=True)

    report_title = st.text_input("Judul report", value="Laporan Analisis Data")

    if st.button("Generate Report", type="primary"):
        quality = st.session_state.last_quality_report if include_quality else None
        if include_quality and quality is None:
            quality = _run_data_quality(df)
            st.session_state.last_quality_report = quality

        lines = []
        lines.append(f"# {report_title}")
        lines.append("")
        lines.append(f"Waktu generate: {datetime.utcnow().isoformat()}Z")
        lines.append("")
        lines.append("## Ringkasan Dataset")
        lines.append(f"- Nama dataset aktif: {st.session_state.dataset_name}")
        lines.append(f"- Shape: {df.shape[0]} baris x {df.shape[1]} kolom")
        lines.append("")

        if quality is not None:
            sc = quality["score"]
            lines.append("## Data Quality")
            lines.append(f"- Quality score: {sc['data_quality_score']}")
            lines.append(f"- Max missing: {sc['max_missing_pct']}%")
            lines.append(f"- Duplicate rows (key): {quality['key_check'].get('duplicate_rows', 0)}")
            lines.append("")

        if include_transform:
            lines.append("## Transform Logs")
            logs = st.session_state.transform_logs[:20]
            if not logs:
                lines.append("- Tidak ada log transform.")
            else:
                for i, log in enumerate(logs, start=1):
                    lines.append(f"{i}. [{log['timestamp']}] {log['title']} :: {json.dumps(log['payload'], ensure_ascii=False)}")
            lines.append("")

        if include_inferential:
            lines.append("## Inferential Logs")
            ilogs = st.session_state.inferential_logs[:20]
            if not ilogs:
                lines.append("- Tidak ada log inferensial.")
            else:
                for i, log in enumerate(ilogs, start=1):
                    payload = log.get("payload", {})
                    pval = payload.get("p_value")
                    ptxt = _fmt_p(float(pval)) if isinstance(pval, (int, float)) else "n/a"
                    lines.append(f"{i}. [{log['timestamp']}] {log['title']} (p={ptxt})")
                    lines.append(f"   - detail: {json.dumps(payload, ensure_ascii=False)}")
            lines.append("")

        md_text = "\n".join(lines)
        html_body = (
            "<html><head><meta charset='utf-8'><title>Report</title></head><body>"
            + "<pre style='font-family: Arial, sans-serif; white-space: pre-wrap'>"
            + md_text.replace("<", "&lt;").replace(">", "&gt;")
            + "</pre></body></html>"
        )

        st.markdown("### Preview")
        st.code(md_text, language="markdown")

        st.download_button(
            "Download Markdown",
            data=md_text.encode("utf-8"),
            file_name="report_analisis.md",
            mime="text/markdown",
        )
        st.download_button(
            "Download HTML",
            data=html_body.encode("utf-8"),
            file_name="report_analisis.html",
            mime="text/html",
        )


def _render_overlay_output() -> None:
    out_df = st.session_state.overlay_result_df
    report = st.session_state.overlay_report

    if out_df is None or report is None:
        return

    st.markdown("### Overlay Report")
    if isinstance(report, dict) and report.get("mode") == "multi":
        summary = {k: v for k, v in report.items() if k != "steps"}
        st.json(summary)

        st.markdown("#### Detail per step")
        for step in report.get("steps", []):
            step_no = step.get("step", "?")
            overlay_name = step.get("overlay_name", "(unknown)")
            with st.expander(f"Step {step_no} • {overlay_name}"):
                st.json(step)
    elif isinstance(report, dict) and report.get("mode") == "single":
        st.json({k: v for k, v in report.items() if k != "report"})
        st.markdown("#### Detail")
        st.json(report.get("report", {}))
    else:
        st.json(report)

    st.markdown("### Hasil Preview")
    st.dataframe(out_df.head(100), use_container_width=True)

    if st.button("Jadikan hasil overlay sebagai dataset aktif", key="set_overlay_as_active"):
        st.session_state.df = out_df
        st.session_state.dataset_name = "overlay_result"
        st.success("Dataset aktif diganti ke hasil overlay.")

    st.markdown("### Download Hasil Overlay")
    fmt = st.selectbox("Format output", options=["sav", "csv", "xlsx", "parquet"], index=0, key="overlay_output_fmt")
    try:
        data, mime, ext = _df_to_download(out_df, fmt)
        st.download_button(
            "Download",
            data=data,
            file_name=f"overlay_result.{ext}",
            mime=mime,
            key="overlay_download_btn",
        )
    except Exception as e:
        st.error(str(e))


def _page_overlay() -> None:
    st.subheader("Overlay / Merge Builder")
    st.caption("Support overlay 2 file atau berantai dari 2+ file (multi overlay).")

    tab_two, tab_multi = st.tabs(["Overlay 2 File", "Overlay 2+ File"])

    with tab_two:
        c1, c2 = st.columns(2)
        with c1:
            up_base = st.file_uploader(
                "Upload Base",
                type=["sav", "csv", "xlsx", "xls", "parquet"],
                key="overlay_base_uploader",
            )
        with c2:
            up_patch = st.file_uploader(
                "Upload Overlay/Patch",
                type=["sav", "csv", "xlsx", "xls", "parquet"],
                key="overlay_patch_uploader",
            )

        if up_base is not None:
            try:
                st.session_state.overlay_base_df = _read_uploaded(up_base)
                st.success(f"Base loaded: {up_base.name}")
            except Exception as e:
                st.error(f"Base error: {e}")

        if up_patch is not None:
            try:
                st.session_state.overlay_patch_df = _read_uploaded(up_patch)
                st.success(f"Patch loaded: {up_patch.name}")
            except Exception as e:
                st.error(f"Patch error: {e}")

        base_df = st.session_state.overlay_base_df
        patch_df = st.session_state.overlay_patch_df

        if base_df is not None and patch_df is not None:
            st.markdown("### Parameter")

            base_cols = list(base_df.columns)
            patch_cols = list(patch_df.columns)
            common_cols = sorted(list(set(base_cols).intersection(set(patch_cols))))

            default_keys = common_cols[:1] if common_cols else base_cols[:1]
            base_keys = st.multiselect(
                "Pilih variabel key dari BASE",
                options=base_cols,
                default=default_keys,
                key="overlay2_base_keys",
            )

            use_key_mapping = st.checkbox(
                "Nama key berbeda antara base & overlay (aktifkan mapping)",
                value=not bool(common_cols),
                key="overlay2_use_mapping",
            )

            key_map: dict[str, str] = {}
            if base_keys:
                if use_key_mapping:
                    st.markdown("#### Mapping key BASE → OVERLAY")
                    for i, bk in enumerate(base_keys):
                        default_overlay_key = bk if bk in patch_cols else patch_cols[min(i, len(patch_cols) - 1)]
                        chosen_overlay_key = st.selectbox(
                            f"Key OVERLAY untuk BASE '{bk}'",
                            options=patch_cols,
                            index=patch_cols.index(default_overlay_key) if default_overlay_key in patch_cols else 0,
                            key=f"overlay2_map_{i}_{bk}",
                        )
                        key_map[bk] = chosen_overlay_key
                else:
                    missing = [k for k in base_keys if k not in patch_cols]
                    if missing:
                        st.error(
                            "Mode mapping dimatikan, tapi key ini tidak ada di overlay: "
                            + ", ".join(missing)
                            + ". Aktifkan mapping key."
                        )
                    for bk in base_keys:
                        key_map[bk] = bk

                if len(set(key_map.values())) < len(key_map.values()):
                    st.warning("Ada key OVERLAY yang dipakai ganda. Sebaiknya 1 key BASE = 1 key OVERLAY.")

            how = st.selectbox("Join mode", options=["left", "inner", "right", "outer"], index=0, key="overlay2_how")
            method = st.selectbox(
                "Overlay method",
                options=["coalesce", "replace", "keep_base", "keep_overlay"],
                index=1,
                key="overlay2_method",
            )
            normalize = st.checkbox("Normalize column names (lowercase_underscore)", value=False, key="overlay2_norm")

            # Untuk menampilkan include/exclude secara realistis, simulasikan rename key overlay -> key base
            simulated_patch = patch_df.copy()
            sim_base_keys = list(base_keys)
            sim_key_map = dict(key_map)
            if normalize:
                simulated_patch = normalize_columns(simulated_patch)
                norm = lambda s: s.strip().lower().replace(" ", "_")
                sim_base_keys = [norm(k) for k in sim_base_keys]
                sim_key_map = {norm(bk): norm(ok) for bk, ok in sim_key_map.items()}

            sim_rename_map = {ov: bk for bk, ov in sim_key_map.items() if ov != bk}
            simulated_patch = simulated_patch.rename(columns=sim_rename_map)
            overlay_non_keys = [c for c in simulated_patch.columns if c not in sim_base_keys]

            include_cols = st.multiselect(
                "Include columns (overlay)",
                options=overlay_non_keys,
                default=[],
                key="overlay2_include",
            )
            exclude_cols = st.multiselect(
                "Exclude columns (overlay)",
                options=overlay_non_keys,
                default=[],
                key="overlay2_exclude",
            )

            if st.button("Run Overlay (2 file)", type="primary", key="run_overlay_two"):
                if not base_keys:
                    st.error("Pilih minimal 1 variabel key dari BASE.")
                elif len(set(key_map.values())) < len(key_map.values()):
                    st.error("Mapping key OVERLAY tidak boleh ganda. Ubah mapping lalu jalankan lagi.")
                else:
                    bdf = base_df.copy()
                    odf = patch_df.copy()

                    run_base_keys = list(base_keys)
                    run_key_map = dict(key_map)
                    run_include = list(include_cols)
                    run_exclude = list(exclude_cols)

                    if normalize:
                        bdf = normalize_columns(bdf)
                        odf = normalize_columns(odf)
                        norm = lambda s: s.strip().lower().replace(" ", "_")
                        run_base_keys = [norm(k) for k in run_base_keys]
                        run_key_map = {norm(bk): norm(ok) for bk, ok in run_key_map.items()}
                        run_include = [norm(c) for c in run_include]
                        run_exclude = [norm(c) for c in run_exclude]

                    rename_map = {ov: bk for bk, ov in run_key_map.items() if ov != bk}
                    odf = odf.rename(columns=rename_map)

                    try:
                        out_df, report = overlay_merge(
                            base_df=bdf,
                            overlay_df=odf,
                            keys=run_base_keys,
                            how=how,
                            method=method,
                            include_cols=run_include,
                            exclude_cols=run_exclude,
                        )
                        st.session_state.overlay_result_df = out_df
                        st.session_state.overlay_report = {
                            "mode": "single",
                            "key_mapping_base_to_overlay": run_key_map,
                            "report": report,
                        }
                        st.success("Overlay 2 file selesai.")
                    except Exception as e:
                        st.error(str(e))
        else:
            st.info("Upload base & overlay dulu.")

    with tab_multi:
        st.caption("Upload minimal 2 file, lalu tentukan base + urutan overlay berantai.")
        uploads = st.file_uploader(
            "Upload multiple datasets",
            type=["sav", "csv", "xlsx", "xls", "parquet"],
            accept_multiple_files=True,
            key="overlay_multi_uploader",
        )

        if uploads:
            loaded: list[dict[str, Any]] = []
            for up in uploads:
                try:
                    df = _read_uploaded(up)
                    loaded.append({"name": up.name, "df": df})
                except Exception as e:
                    st.error(f"Gagal baca {up.name}: {e}")
            st.session_state.overlay_multi_data = loaded

        multi_data = st.session_state.overlay_multi_data
        if not multi_data or len(multi_data) < 2:
            st.info("Upload minimal 2 file untuk mode multi overlay.")
        else:
            summary = pd.DataFrame(
                [
                    {
                        "file": item["name"],
                        "rows": len(item["df"]),
                        "columns": len(item["df"].columns),
                    }
                    for item in multi_data
                ]
            )
            st.dataframe(summary, use_container_width=True)

            names = [x["name"] for x in multi_data]
            base_name = st.selectbox("Pilih base file", options=names, index=0, key="overlay_multi_base")

            how = st.selectbox("Join mode", options=["left", "inner", "right", "outer"], index=0, key="overlay_multi_how")
            method = st.selectbox(
                "Overlay method",
                options=["coalesce", "replace", "keep_base", "keep_overlay"],
                index=1,
                key="overlay_multi_method",
            )
            normalize = st.checkbox(
                "Normalize column names (lowercase_underscore)",
                value=False,
                key="overlay_multi_norm",
            )

            prepared_data: list[dict[str, Any]] = []
            for item in multi_data:
                df = item["df"].copy()
                if normalize:
                    df = normalize_columns(df)
                prepared_data.append({"name": item["name"], "df": df})

            base_idx = names.index(base_name)
            base_df = prepared_data[base_idx]["df"]
            base_cols = list(base_df.columns)
            default_base_keys = base_cols[:1]
            base_keys = st.multiselect(
                "Pilih variabel key dari BASE",
                options=base_cols,
                default=default_base_keys,
                key="overlay_multi_base_keys",
            )

            overlay_indices = [i for i in range(len(prepared_data)) if i != base_idx]
            ordered_overlay_names = [prepared_data[i]["name"] for i in overlay_indices]
            st.caption(f"Urutan overlay: {' -> '.join(ordered_overlay_names)}")

            use_key_mapping_multi = st.checkbox(
                "Nama key antar file bisa berbeda (aktifkan mapping per file)",
                value=True,
                key="overlay_multi_use_mapping",
            )

            key_maps_per_file: dict[str, dict[str, str]] = {}
            mapping_errors: list[str] = []

            if base_keys:
                st.markdown("#### Mapping key per file overlay")
                for idx in overlay_indices:
                    overlay_name = prepared_data[idx]["name"]
                    overlay_cols = list(prepared_data[idx]["df"].columns)
                    per_map: dict[str, str] = {}

                    if use_key_mapping_multi:
                        with st.expander(f"Mapping: {overlay_name}", expanded=False):
                            for j, bk in enumerate(base_keys):
                                default_overlay_key = bk if bk in overlay_cols else overlay_cols[min(j, len(overlay_cols) - 1)]
                                chosen_overlay_key = st.selectbox(
                                    f"{overlay_name} → key untuk BASE '{bk}'",
                                    options=overlay_cols,
                                    index=overlay_cols.index(default_overlay_key) if default_overlay_key in overlay_cols else 0,
                                    key=f"overlay_multi_map_{idx}_{j}_{bk}",
                                )
                                per_map[bk] = chosen_overlay_key
                    else:
                        missing = [k for k in base_keys if k not in overlay_cols]
                        if missing:
                            mapping_errors.append(
                                f"{overlay_name}: key tidak ditemukan ({', '.join(missing)}). Aktifkan mapping per file."
                            )
                        for bk in base_keys:
                            per_map[bk] = bk

                    if len(set(per_map.values())) < len(per_map.values()):
                        mapping_errors.append(f"{overlay_name}: ada key overlay yang dipakai ganda.")

                    key_maps_per_file[overlay_name] = per_map

            if mapping_errors:
                for msg in mapping_errors:
                    st.error(msg)

            # Hitung opsi include/exclude dari semua file overlay setelah simulasi rename key
            union_overlay_cols: set[str] = set()
            for idx in overlay_indices:
                overlay_name = prepared_data[idx]["name"]
                odf = prepared_data[idx]["df"].copy()
                per_map = key_maps_per_file.get(overlay_name, {})
                rename_map = {ov: bk for bk, ov in per_map.items() if ov != bk}
                odf = odf.rename(columns=rename_map)
                union_overlay_cols.update([c for c in odf.columns if c not in base_keys])

            include_cols = st.multiselect(
                "Include columns (opsional, dari semua file overlay)",
                options=sorted(union_overlay_cols),
                default=[],
                key="overlay_multi_include",
            )
            exclude_cols = st.multiselect(
                "Exclude columns (opsional)",
                options=sorted(union_overlay_cols),
                default=[],
                key="overlay_multi_exclude",
            )

            if st.button("Run Overlay (2+ file)", type="primary", key="run_overlay_multi"):
                if not base_keys:
                    st.error("Pilih minimal 1 variabel key dari BASE.")
                elif mapping_errors:
                    st.error("Masih ada error mapping key. Perbaiki dulu sebelum run.")
                else:
                    current_df = prepared_data[base_idx]["df"].copy()
                    steps: list[dict[str, Any]] = []

                    for step_no, idx in enumerate(overlay_indices, start=1):
                        overlay_name = prepared_data[idx]["name"]
                        overlay_df = prepared_data[idx]["df"].copy()
                        per_map = key_maps_per_file.get(overlay_name, {})

                        rename_map = {ov: bk for bk, ov in per_map.items() if ov != bk}
                        overlay_df = overlay_df.rename(columns=rename_map)

                        step_include = [c for c in include_cols if c in overlay_df.columns and c not in base_keys]
                        step_exclude = [c for c in exclude_cols if c in overlay_df.columns and c not in base_keys]

                        candidate_cols = (
                            step_include
                            if include_cols
                            else [c for c in overlay_df.columns if c not in base_keys and c not in step_exclude]
                        )

                        if not candidate_cols:
                            steps.append(
                                {
                                    "step": step_no,
                                    "overlay_name": overlay_name,
                                    "skipped": True,
                                    "reason": "Tidak ada kolom overlay yang valid untuk step ini.",
                                }
                            )
                            continue

                        try:
                            out_df, rep = overlay_merge(
                                base_df=current_df,
                                overlay_df=overlay_df,
                                keys=list(base_keys),
                                how=how,
                                method=method,
                                include_cols=step_include,
                                exclude_cols=step_exclude,
                            )
                            rep["step"] = step_no
                            rep["overlay_name"] = overlay_name
                            rep["key_mapping_base_to_overlay"] = per_map
                            rep["skipped"] = False
                            steps.append(rep)
                            current_df = out_df
                        except Exception as e:
                            steps.append(
                                {
                                    "step": step_no,
                                    "overlay_name": overlay_name,
                                    "key_mapping_base_to_overlay": per_map,
                                    "skipped": True,
                                    "reason": str(e),
                                }
                            )

                    st.session_state.overlay_result_df = current_df
                    st.session_state.overlay_report = {
                        "mode": "multi",
                        "base_file": base_name,
                        "input_files": names,
                        "keys": list(base_keys),
                        "how": how,
                        "method": method,
                        "steps": steps,
                    }
                    st.success("Overlay multi-file selesai.")

    _render_overlay_output()

def _page_export() -> None:
    st.subheader("Export Dataset Aktif")
    df = _require_df()
    if df is None:
        return

    fmt = st.selectbox("Format", options=["sav", "csv", "xlsx", "parquet"], index=1)
    base_name = st.text_input("Nama file (tanpa ekstensi)", value="dataset_hasil_analisis")

    try:
        payload, mime, ext = _df_to_download(df, fmt)
        st.download_button(
            "Download dataset",
            data=payload,
            file_name=f"{base_name}.{ext}",
            mime=mime,
        )
    except Exception as e:
        st.error(str(e))


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    ensure_state()

    st.title(APP_TITLE)
    st.caption("UI/UX analisis data untuk workflow yang familiar dengan SPSS.")

    if not _auth_gate():
        st.stop()

    with st.sidebar:
        st.markdown("## Menu")
        page = st.radio(
            "Pilih fitur",
            options=[
                "Dataset",
                "Variable View",
                "Data Quality",
                "Transform",
                "Descriptive",
                "Frequencies",
                "Crosstabs",
                "Correlation",
                "Inferential",
                "Charts",
                "Overlay",
                "Export",
                "Report",
            ],
        )

        st.markdown("---")
        active = st.session_state.dataset_name or "(belum ada)"
        st.caption(f"Dataset aktif: {active}")

        if st.session_state.df is not None:
            st.caption(f"Shape: {st.session_state.df.shape[0]:,} x {st.session_state.df.shape[1]:,}")

        st.caption(f"Max upload: {MAX_UPLOAD_MB} MB")
        if st.button("Reset overlay cache", key="reset_overlay_cache"):
            st.session_state.overlay_base_df = None
            st.session_state.overlay_patch_df = None
            st.session_state.overlay_multi_data = None
            st.session_state.overlay_result_df = None
            st.session_state.overlay_report = None
            st.success("Cache overlay direset.")

    if page == "Dataset":
        _page_dataset()
    elif page == "Variable View":
        _page_variable_view()
    elif page == "Data Quality":
        _page_quality()
    elif page == "Transform":
        _page_transform()
    elif page == "Descriptive":
        _page_descriptive()
    elif page == "Frequencies":
        _page_frequency()
    elif page == "Crosstabs":
        _page_crosstab()
    elif page == "Correlation":
        _page_correlation()
    elif page == "Inferential":
        _page_inferential()
    elif page == "Charts":
        _page_charts()
    elif page == "Overlay":
        _page_overlay()
    elif page == "Export":
        _page_export()
    elif page == "Report":
        _page_report()

    with st.expander("Tentang UI ini"):
        info = {
            "fokus": "Workflow analisis data cepat ala SPSS",
            "fitur_utama": [
                "Data quality checks",
                "Transform tools (recode/compute/binning/missing/filter)",
                "Descriptive/Frequencies/Crosstabs/Correlation",
                "Inferential stats (t-test, chi-square, ANOVA, linear/logistic regression)",
                "Overlay builder (2 file & multi-file) + export",
                "Report generator (Markdown/HTML)",
            ],
            "catatan": "Untuk keamanan publik, gunakan HTTPS + auth di reverse proxy.",
        }
        st.code(json.dumps(info, ensure_ascii=False, indent=2), language="json")


if __name__ == "__main__":
    main()
