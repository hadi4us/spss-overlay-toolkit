#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(optparse)
  library(dplyr)
  library(haven)
  library(readr)
  library(jsonlite)
})

parse_csv_list <- function(x) {
  if (is.null(x) || x == "") return(character(0))
  parts <- strsplit(x, ",", fixed = TRUE)[[1]]
  trimws(parts[nzchar(trimws(parts))])
}

get_ext <- function(path) {
  tolower(tools::file_ext(path))
}

read_table <- function(path) {
  ex <- get_ext(path)
  if (ex == "sav") return(read_sav(path))
  if (ex == "csv") return(read_csv(path, show_col_types = FALSE))
  stop(sprintf("Format input tidak didukung: %s", path))
}

write_table <- function(df, path) {
  dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
  ex <- get_ext(path)
  if (ex == "sav") {
    write_sav(df, path)
    return(invisible(NULL))
  }
  if (ex == "csv") {
    write_csv(df, path)
    return(invisible(NULL))
  }
  stop(sprintf("Format output tidak didukung: %s", path))
}

normalize_columns <- function(df) {
  names(df) <- gsub(" +", "_", tolower(trimws(names(df))))
  df
}

check_keys <- function(df, keys, label) {
  missing <- setdiff(keys, names(df))
  if (length(missing) > 0) {
    stop(sprintf("Kolom key tidak ditemukan di %s: %s", label, paste(missing, collapse = ", ")))
  }
}

option_list <- list(
  make_option("--base", type = "character", help = "File base (.sav/.csv)", metavar = "FILE"),
  make_option("--overlay", type = "character", help = "File overlay (.sav/.csv)", metavar = "FILE"),
  make_option("--keys", type = "character", help = "Kolom key (koma), contoh: id atau id,tanggal"),
  make_option("--output", type = "character", help = "Output (.sav/.csv)", metavar = "FILE"),
  make_option("--report", type = "character", default = NULL, help = "Output JSON report"),
  make_option("--how", type = "character", default = "left", help = "left|inner|right|full [default %default]"),
  make_option("--method", type = "character", default = "coalesce", help = "coalesce|replace|keep_base|keep_overlay [default %default]"),
  make_option("--include-cols", type = "character", default = NULL, help = "Kolom overlay yang dipakai (koma). Default semua"),
  make_option("--exclude-cols", type = "character", default = NULL, help = "Kolom overlay yang dibuang (koma)"),
  make_option("--normalize-cols", action = "store_true", default = FALSE, help = "Normalisasi nama kolom")
)

parser <- OptionParser(option_list = option_list)
opt <- parse_args(parser)

required <- c("base", "overlay", "keys", "output")
for (r in required) {
  if (is.null(opt[[r]]) || opt[[r]] == "") {
    print_help(parser)
    stop(sprintf("Argumen --%s wajib diisi", r))
  }
}

keys <- parse_csv_list(opt$keys)
include_cols <- parse_csv_list(opt$`include-cols`)
exclude_cols <- parse_csv_list(opt$`exclude-cols`)

base_df <- read_table(opt$base)
overlay_df <- read_table(opt$overlay)

if (opt$`normalize-cols`) {
  base_df <- normalize_columns(base_df)
  overlay_df <- normalize_columns(overlay_df)
  keys <- gsub(" +", "_", tolower(trimws(keys)))
  include_cols <- gsub(" +", "_", tolower(trimws(include_cols)))
  exclude_cols <- gsub(" +", "_", tolower(trimws(exclude_cols)))
}

check_keys(base_df, keys, "base")
check_keys(overlay_df, keys, "overlay")

base_non_keys <- setdiff(names(base_df), keys)
if (length(include_cols) > 0) {
  overlay_cols <- setdiff(intersect(include_cols, names(overlay_df)), keys)
} else {
  overlay_cols <- setdiff(names(overlay_df), keys)
}
if (length(exclude_cols) > 0) {
  overlay_cols <- setdiff(overlay_cols, exclude_cols)
}
if (length(overlay_cols) == 0) {
  stop("Tidak ada kolom overlay yang dipilih. Cek include/exclude.")
}

overlay_uniq <- overlay_df %>%
  select(all_of(c(keys, overlay_cols))) %>%
  distinct(across(all_of(keys)), .keep_all = TRUE)

join_fn <- switch(
  opt$how,
  left = left_join,
  inner = inner_join,
  right = right_join,
  full = full_join,
  stop("--how harus salah satu: left|inner|right|full")
)

merged <- join_fn(base_df, overlay_uniq, by = keys, suffix = c("_base", "_ovr"))

overlap_cols <- intersect(overlay_cols, base_non_keys)

for (col in overlap_cols) {
  c_base <- paste0(col, "_base")
  c_ovr <- paste0(col, "_ovr")

  if (opt$method == "coalesce") {
    merged[[col]] <- dplyr::coalesce(merged[[c_base]], merged[[c_ovr]])
  } else if (opt$method == "replace") {
    merged[[col]] <- dplyr::coalesce(merged[[c_ovr]], merged[[c_base]])
  } else if (opt$method == "keep_base") {
    merged[[col]] <- merged[[c_base]]
  } else if (opt$method == "keep_overlay") {
    merged[[col]] <- merged[[c_ovr]]
  } else {
    stop("--method harus salah satu: coalesce|replace|keep_base|keep_overlay")
  }
}

# Rename kolom non-overlap yang kena suffix
for (n in names(merged)) {
  if (grepl("_base$", n)) {
    original <- sub("_base$", "", n)
    if (!(original %in% overlap_cols)) {
      names(merged)[names(merged) == n] <- original
    }
  }
}
for (n in names(merged)) {
  if (grepl("_ovr$", n)) {
    original <- sub("_ovr$", "", n)
    if (!(original %in% overlap_cols) && !(original %in% names(base_df))) {
      names(merged)[names(merged) == n] <- original
    }
  }
}

# Drop kolom suffix overlap
drop_cols <- c(paste0(overlap_cols, "_base"), paste0(overlap_cols, "_ovr"))
merged <- merged %>% select(-any_of(drop_cols))

matched_n <- nrow(semi_join(base_df, overlay_uniq, by = keys))
unmatched_base_n <- nrow(anti_join(base_df, overlay_uniq, by = keys))
unmatched_overlay_n <- nrow(anti_join(overlay_uniq, base_df, by = keys))

report <- list(
  base_rows = nrow(base_df),
  overlay_rows = nrow(overlay_df),
  overlay_rows_after_dedup = nrow(overlay_uniq),
  output_rows = nrow(merged),
  matched_in_base = matched_n,
  unmatched_in_base = unmatched_base_n,
  unmatched_in_overlay = unmatched_overlay_n,
  keys = keys,
  how = opt$how,
  method = opt$method,
  overlay_columns_used = overlay_cols,
  overlap_columns = overlap_cols
)

write_table(merged, opt$output)

if (!is.null(opt$report) && nzchar(opt$report)) {
  dir.create(dirname(opt$report), recursive = TRUE, showWarnings = FALSE)
  write(toJSON(report, auto_unbox = TRUE, pretty = TRUE), file = opt$report)
}

cat("[OK] Overlay selesai\n")
cat(toJSON(report, auto_unbox = TRUE, pretty = TRUE), "\n")
