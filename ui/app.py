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
        "overlay_multi_data": None,
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
