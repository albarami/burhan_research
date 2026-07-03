# Burhān R preparation worker (FR-501; PB-02/03/04; AT-M08-6).
#
# The R half of the dual preparation path, written from the governed
# sequence semantics and the call payload — independent of the Python
# implementation. Sequence: consent -> duplicates (policy keys, drop
# later keep first) -> attention checks -> straight-liners (zero variance
# across a contiguous answered run of >= policy block length, instrument
# order) -> completion profiling with recovery at the policy threshold ->
# range enforcement (out-of-range and unparseable cells become NA; cases
# stay) -> reverse coding -> outlier treatment per policy (retain keeps
# every case; remove drops flagged cases by |z| beyond the policy
# criterion or Mahalanobis D2 beyond the chi-square criterion).
#
# Payload (see build_r_payload): csv_path, header_rows, id_column,
# consent_column, attention_checks, items (code/column/min/max/reverse in
# instrument order), policy rules. Result: item columns, final case keys
# (repeated export ids suffixed #n), cells row-major with NA as null, and
# the N-chain drop counts per link.
#
# No cell is ever filled and no case is ever fabricated (FR-505).

run_worker <- function(payload) {
  policy <- payload$policy
  raw <- utils::read.csv(
    payload$csv_path,
    colClasses = "character",
    header = FALSE,
    check.names = FALSE,
    na.strings = character(0)
  )
  codes <- as.character(unlist(raw[1L, ]))
  header_rows <- as.integer(payload$header_rows)
  data <- raw[seq.int(header_rows + 1L, nrow(raw)), , drop = FALSE]

  column_index <- function(name) {
    index <- match(name, codes)
    stopifnot(!is.na(index))
    index
  }
  id_index <- column_index(payload$id_column)
  item_codes <- vapply(payload$items, function(item) item$code, character(1L))
  item_columns <- vapply(
    payload$items,
    function(item) column_index(item$column),
    integer(1L)
  )
  item_min <- vapply(
    payload$items, function(item) as.numeric(item$min), numeric(1L)
  )
  item_max <- vapply(
    payload$items, function(item) as.numeric(item$max), numeric(1L)
  )
  item_reverse <- vapply(
    payload$items, function(item) isTRUE(item$reverse), logical(1L)
  )

  # case keys: export ids, occurrence-suffixed on repeats
  ids <- as.character(data[[id_index]])
  occurrence <- stats::ave(seq_along(ids), ids, FUN = seq_along)
  keys <- ifelse(occurrence == 1L, ids, paste0(ids, "#", occurrence))
  keep <- rep(TRUE, nrow(data))
  dropped <- list(
    consent = 0L, duplicates = 0L, attention_checks = 0L,
    straight_liners = 0L, partial_recovery = 0L, outlier_policy = 0L
  )

  raw_cell <- function(row, column) as.character(data[row, column])
  cell <- function(row, column) trimws(raw_cell(row, column))

  # -- consent -----------------------------------------------------------------
  if (!is.null(payload$consent_column)) {
    consent_index <- column_index(payload$consent_column)
    refused <- keep & (as.character(data[[consent_index]]) != "1")
    dropped$consent <- sum(refused)
    keep <- keep & !refused
  }

  # -- duplicates (policy keys; drop later, keep first) ------------------
  duplicate_keys <- unlist(policy$duplicate_keys)
  is_duplicate <- rep(FALSE, nrow(data))
  if ("response_id" %in% duplicate_keys) {
    seen <- character(0L)
    for (row in which(keep)) {
      if (ids[[row]] %in% seen) {
        is_duplicate[[row]] <- TRUE
      } else {
        seen <- c(seen, ids[[row]])
      }
    }
  }
  if ("identical_model_vector" %in% duplicate_keys) {
    seen_vectors <- character(0L)
    for (row in which(keep)) {
      if (is_duplicate[[row]]) next
      vector_key <- paste(
        vapply(
          item_columns, function(column) raw_cell(row, column), character(1L)
        ),
        collapse = "\x1f"
      )
      if (vector_key %in% seen_vectors) {
        is_duplicate[[row]] <- TRUE
      } else {
        seen_vectors <- c(seen_vectors, vector_key)
      }
    }
  }
  dropped$duplicates <- sum(is_duplicate & keep)
  keep <- keep & !is_duplicate

  # -- attention checks --------------------------------------------------
  failed_attention <- rep(FALSE, nrow(data))
  for (check in payload$attention_checks) {
    check_index <- column_index(check$column)
    for (row in which(keep)) {
      if (as.character(data[row, check_index]) != check$expected) {
        failed_attention[[row]] <- TRUE
      }
    }
  }
  if (identical(policy$attention_action, "drop")) {
    dropped$attention_checks <- sum(failed_attention & keep)
    keep <- keep & !failed_attention
  }

  # -- straight-liners ---------------------------------------------------
  stopifnot(
    identical(policy$straightliner_method, "zero_variance_within_block")
  )
  block <- as.integer(policy$straightliner_min_block)
  parse_cell <- function(row, column) {
    value <- cell(row, column)
    if (identical(value, "")) return(NA_real_)
    suppressWarnings(as.numeric(value))
  }
  is_liner <- rep(FALSE, nrow(data))
  for (row in which(keep)) {
    run_value <- NA_real_
    run_length <- 0L
    for (column in item_columns) {
      value <- parse_cell(row, column)
      if (is.na(value)) {
        run_value <- NA_real_
        run_length <- 0L
        next
      }
      if (!is.na(run_value) && value == run_value) {
        run_length <- run_length + 1L
      } else {
        run_value <- value
        run_length <- 1L
      }
      if (run_length >= block) {
        is_liner[[row]] <- TRUE
        break
      }
    }
  }
  if (identical(policy$straightliner_action, "drop")) {
    dropped$straight_liners <- sum(is_liner & keep)
    keep <- keep & !is_liner
  }

  # -- completion profiling and partial recovery -------------------------
  stopifnot(identical(policy$completion_basis, "model_items"))
  threshold <- as.numeric(policy$min_completion_pct)
  below <- rep(FALSE, nrow(data))
  for (row in which(keep)) {
    answered <- sum(vapply(
      item_columns,
      function(column) !identical(cell(row, column), ""),
      logical(1L)
    ))
    pct <- 100 * answered / length(item_columns)
    if (pct < threshold) below[[row]] <- TRUE
  }
  dropped$partial_recovery <- sum(below & keep)
  keep <- keep & !below

  # -- typed matrix, range enforcement, reverse coding -------------------
  rows_kept <- which(keep)
  cells <- matrix(
    NA_real_,
    nrow = length(rows_kept),
    ncol = length(item_columns)
  )
  for (position in seq_along(rows_kept)) {
    row <- rows_kept[[position]]
    for (item in seq_along(item_columns)) {
      value <- parse_cell(row, item_columns[[item]])
      if (!is.na(value) &&
            (value < item_min[[item]] || value > item_max[[item]])) {
        value <- NA_real_
      }
      cells[position, item] <- value
    }
  }
  for (item in seq_along(item_columns)) {
    if (item_reverse[[item]]) {
      cells[, item] <- (item_min[[item]] + item_max[[item]]) - cells[, item]
    }
  }

  # -- outlier treatment per policy --------------------------------------
  treatment <- policy$outlier_treatment
  if (identical(treatment, "remove_with_sensitivity")) {
    flagged <- rep(FALSE, nrow(cells))
    for (item in seq_len(ncol(cells))) {
      column_values <- cells[, item]
      spread <- stats::sd(column_values, na.rm = TRUE)
      if (is.na(spread) || spread <= 0) next
      z <- (column_values - mean(column_values, na.rm = TRUE)) / spread
      criterion_z <- as.numeric(policy$univariate_z)
      flagged <- flagged | (!is.na(z) & abs(z) > criterion_z)
    }
    complete <- stats::complete.cases(cells)
    if (sum(complete) > ncol(cells)) {
      complete_cells <- cells[complete, , drop = FALSE]
      d2 <- stats::mahalanobis(
        complete_cells,
        colMeans(complete_cells),
        stats::cov(complete_cells)
      )
      p_criterion <- as.numeric(policy$mahalanobis_p)
      criterion <- stats::qchisq(1 - p_criterion, df = ncol(cells))
      flagged[complete] <- flagged[complete] | (d2 > criterion)
    }
    dropped$outlier_policy <- sum(flagged)
    cells <- cells[!flagged, , drop = FALSE]
    rows_kept <- rows_kept[!flagged]
  } else {
    stopifnot(identical(treatment, "retain_with_sensitivity"))
  }

  cell_rows <- lapply(seq_len(nrow(cells)), function(row) {
    lapply(seq_len(ncol(cells)), function(column) {
      value <- cells[row, column]
      if (is.na(value)) NULL else value
    })
  })
  list(
    columns = as.list(item_codes),
    cases = as.list(keys[rows_kept]),
    cells = cell_rows,
    n_chain = list(
      raw_n = nrow(data),
      final_n = length(rows_kept),
      dropped_by_link = dropped
    )
  )
}
