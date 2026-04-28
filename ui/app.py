#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from overlay_sav import normalize_columns, overlay_merge, parse_csv_list  # noqa: E402

try:
    import pyreadstat
except ImportError:  # pragma: no cover
    pyreadstat = None

APP_TITLE = "SPSS-Like Data Studio"


def ensure_state() -> None:
    defaults: dict[str, Any] = {
        "df": None,
        "dataset_name": None,
        "overlay_base_df": None,
        "overlay_patch_df": None,
        "overlay_report": None,
        "overlay_result_df": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _ext(name: str) -> str:
    return Path(name).suffix.lower()


def _read_uploaded(uploaded_file) -> pd.DataFrame:
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


def _page_overlay() -> None:
    st.subheader("Overlay / Merge Builder")
    st.caption("Mirip proses update data SPSS: base dataset + patch dataset + key")

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

    if base_df is None or patch_df is None:
        st.info("Upload base & overlay dulu.")
        return

    common_cols = sorted(list(set(base_df.columns).intersection(set(patch_df.columns))))
    if not common_cols:
        st.error("Tidak ada nama kolom yang sama antara base dan overlay.")
        return

    st.markdown("### Parameter")
    keys = st.multiselect("Keys", options=common_cols, default=common_cols[:1])
    how = st.selectbox("Join mode", options=["left", "inner", "right", "outer"], index=0)
    method = st.selectbox("Overlay method", options=["coalesce", "replace", "keep_base", "keep_overlay"], index=1)
    normalize = st.checkbox("Normalize column names (lowercase_underscore)", value=False)

    overlay_non_keys = [c for c in patch_df.columns if c not in keys]
    include_cols = st.multiselect("Include columns (overlay)", options=overlay_non_keys, default=[])
    exclude_cols = st.multiselect("Exclude columns (overlay)", options=overlay_non_keys, default=[])

    if st.button("Run Overlay", type="primary"):
        if not keys:
            st.error("Pilih minimal 1 key.")
            return

        bdf = base_df.copy()
        odf = patch_df.copy()

        sel_keys = list(keys)
        sel_include = list(include_cols)
        sel_exclude = list(exclude_cols)

        if normalize:
            bdf = normalize_columns(bdf)
            odf = normalize_columns(odf)
            sel_keys = parse_csv_list(",".join([k.strip().lower().replace(" ", "_") for k in sel_keys]))
            sel_include = parse_csv_list(",".join([c.strip().lower().replace(" ", "_") for c in sel_include]))
            sel_exclude = parse_csv_list(",".join([c.strip().lower().replace(" ", "_") for c in sel_exclude]))

        try:
            out_df, report = overlay_merge(
                base_df=bdf,
                overlay_df=odf,
                keys=sel_keys,
                how=how,
                method=method,
                include_cols=sel_include,
                exclude_cols=sel_exclude,
            )
            st.session_state.overlay_result_df = out_df
            st.session_state.overlay_report = report
            st.success("Overlay selesai.")
        except Exception as e:
            st.error(str(e))
            return

    out_df = st.session_state.overlay_result_df
    report = st.session_state.overlay_report

    if out_df is not None and report is not None:
        st.markdown("### Overlay Report")
        st.json(report)

        st.markdown("### Hasil Preview")
        st.dataframe(out_df.head(100), use_container_width=True)

        if st.button("Jadikan hasil overlay sebagai dataset aktif"):
            st.session_state.df = out_df
            st.session_state.dataset_name = "overlay_result"
            st.success("Dataset aktif diganti ke hasil overlay.")

        st.markdown("### Download Hasil Overlay")
        fmt = st.selectbox("Format output", options=["sav", "csv", "xlsx", "parquet"], index=0)
        try:
            data, mime, ext = _df_to_download(out_df, fmt)
            st.download_button(
                "Download",
                data=data,
                file_name=f"overlay_result.{ext}",
                mime=mime,
            )
        except Exception as e:
            st.error(str(e))


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

    with st.sidebar:
        st.markdown("## Menu")
        page = st.radio(
            "Pilih fitur",
            options=[
                "Dataset",
                "Variable View",
                "Descriptive",
                "Frequencies",
                "Crosstabs",
                "Correlation",
                "Charts",
                "Overlay",
                "Export",
            ],
        )

        st.markdown("---")
        active = st.session_state.dataset_name or "(belum ada)"
        st.caption(f"Dataset aktif: {active}")

        if st.session_state.df is not None:
            st.caption(f"Shape: {st.session_state.df.shape[0]:,} x {st.session_state.df.shape[1]:,}")

    if page == "Dataset":
        _page_dataset()
    elif page == "Variable View":
        _page_variable_view()
    elif page == "Descriptive":
        _page_descriptive()
    elif page == "Frequencies":
        _page_frequency()
    elif page == "Crosstabs":
        _page_crosstab()
    elif page == "Correlation":
        _page_correlation()
    elif page == "Charts":
        _page_charts()
    elif page == "Overlay":
        _page_overlay()
    elif page == "Export":
        _page_export()

    with st.expander("Tentang UI ini"):
        info = {
            "fokus": "Workflow analisis data cepat ala SPSS",
            "fitur_utama": [
                "Variable view",
                "Descriptive/Frequencies/Crosstabs",
                "Correlation + chart interaktif",
                "Overlay builder + export",
            ],
            "catatan": "Untuk analisis inferensial lanjutan (ANOVA/regresi kompleks), bisa ditambahkan pada iterasi berikutnya.",
        }
        st.code(json.dumps(info, ensure_ascii=False, indent=2), language="json")


if __name__ == "__main__":
    main()
