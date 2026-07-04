# Burhān R effects worker (FR-802; PB-17; AT-M11-2/3).
#
# op "effects": { cells, columns, constructs ([] = observed path model),
#   second_order, approach, carrier, regressions: [{lhs, rhs}],
#   indirect: [{id, from, to, via: [..]}],
#   bootstrap: {resamples, ci_level, ci_type} }
#
# Every regression edge is labeled p_<lhs>_<rhs>; each indirect spec
# defines ind_<id> as the product along its via chain (per-path
# decomposition for multi-mediator chains), tot_<id> as ind + direct
# when the direct edge exists, and a sum of specific indirects per
# (from, to) group with more than one spec. Estimation is one
# lavaan::sem fit with bootstrap standard errors; CIs use the requested
# type (bias_corrected -> bca.simple, percentile -> perc) at the
# requested level. The harness seeds the RNG before this runs, so
# identical seeds reproduce identical draws. Malformed inputs and
# non-converged fits abort loudly.

.effects_data <- function(payload) {
  columns <- unlist(payload$columns)
  rows <- payload$cells
  data <- matrix(NA_real_, nrow = length(rows), ncol = length(columns))
  for (row_index in seq_along(rows)) {
    row <- rows[[row_index]]
    for (column_index in seq_along(columns)) {
      value <- row[[column_index]]
      if (!is.null(value)) data[row_index, column_index] <- as.numeric(value)
    }
  }
  data <- as.data.frame(data)
  names(data) <- columns
  stopifnot(all(stats::complete.cases(data)))
  data
}

.measurement_syntax <- function(constructs, second) {
  if (length(constructs) == 0L) {
    stopifnot(is.null(second))
    return(NULL)
  }
  lines <- vapply(constructs, function(construct) {
    paste0(
      construct$code, " =~ ",
      paste(unlist(construct$indicators), collapse = " + ")
    )
  }, character(1L))
  if (!is.null(second)) {
    lines <- c(lines, paste0(
      second$code, " =~ ",
      paste(unlist(second$components), collapse = " + ")
    ))
  }
  paste(lines, collapse = "\n")
}

.edge_label <- function(lhs, rhs) paste0("p_", lhs, "_", rhs)

.labeled_regressions <- function(regressions) {
  lhs_all <- vapply(regressions, function(r) r$lhs, character(1L))
  lines <- vapply(unique(lhs_all), function(lhs) {
    terms <- unlist(lapply(regressions, function(r) {
      if (!identical(r$lhs, lhs)) {
        return(NULL)
      }
      paste0(.edge_label(lhs, r$rhs), "*", r$rhs)
    }))
    paste0(lhs, " ~ ", paste(terms, collapse = " + "))
  }, character(1L))
  paste(lines, collapse = "\n")
}

.chain_labels <- function(spec, edge_set) {
  chain <- c(spec$from, unlist(spec$via), spec$to)
  labels <- character(length(chain) - 1L)
  for (i in seq_len(length(chain) - 1L)) {
    lhs <- chain[[i + 1L]]
    rhs <- chain[[i]]
    stopifnot(paste(lhs, rhs) %in% edge_set)
    labels[[i]] <- .edge_label(lhs, rhs)
  }
  labels
}

.block_from <- function(row) {
  p_value <- row$pvalue
  list(
    est = row$est,
    se = row$se,
    ci_low = row$ci.lower,
    ci_high = row$ci.upper,
    p = if (is.na(p_value)) NULL else p_value
  )
}

run_worker <- function(payload) {
  stopifnot(identical(payload$op, "effects"))
  carrier <- payload$carrier
  if (!is.null(carrier) && !identical(carrier, "full_hierarchy")) {
    stop("effects_worker: unsupported carrier '", carrier, "'")
  }
  data <- .effects_data(payload)
  regressions <- payload$regressions
  specs <- payload$indirect
  bootstrap <- payload$bootstrap
  stopifnot(length(regressions) >= 1L, length(specs) >= 1L)
  resamples <- as.integer(bootstrap$resamples)
  ci_level <- as.numeric(bootstrap$ci_level)
  ci_type <- bootstrap$ci_type
  boot_type <- if (identical(ci_type, "bias_corrected")) {
    "bca.simple"
  } else if (identical(ci_type, "percentile")) {
    "perc"
  } else {
    stop("effects_worker: unknown ci_type '", ci_type, "'")
  }

  edge_set <- vapply(
    regressions, function(r) paste(r$lhs, r$rhs), character(1L)
  )
  measurement <- .measurement_syntax(payload$constructs, payload$second_order)
  reg_syntax <- .labeled_regressions(regressions)
  definitions <- character(0L)
  products <- list()
  for (spec in specs) {
    labels <- .chain_labels(spec, edge_set)
    product <- paste(labels, collapse = "*")
    products[[spec$id]] <- list(spec = spec, product = product)
    definitions <- c(definitions, paste0("ind_", spec$id, " := ", product))
    if (paste(spec$to, spec$from) %in% edge_set) {
      definitions <- c(definitions, paste0(
        "tot_", spec$id, " := ", product, " + ",
        .edge_label(spec$to, spec$from)
      ))
    }
  }
  groups <- list()
  for (entry in products) {
    key <- paste(entry$spec$from, entry$spec$to)
    groups[[key]] <- c(groups[[key]], entry$product)
  }
  sum_keys <- names(groups)[vapply(groups, length, integer(1L)) > 1L]
  for (key in sum_keys) {
    parts <- strsplit(key, " ")[[1L]]
    definitions <- c(definitions, paste0(
      "sum_", parts[[1L]], "_", parts[[2L]], " := ",
      paste(groups[[key]], collapse = " + ")
    ))
  }
  syntax <- paste(
    c(measurement, reg_syntax, definitions),
    collapse = "\n"
  )

  fit <- lavaan::sem(
    syntax,
    data = data,
    meanstructure = TRUE,
    se = "bootstrap",
    bootstrap = resamples
  )
  stopifnot(isTRUE(lavaan::lavInspect(fit, "converged")))
  completed <- nrow(lavaan::lavInspect(fit, "boot"))
  pe <- lavaan::parameterEstimates(
    fit, boot.ci.type = boot_type, level = ci_level
  )

  reg_rows <- pe[pe$op == "~", ]
  paths <- vector("list", nrow(reg_rows))
  for (i in seq_len(nrow(reg_rows))) {
    row <- reg_rows[i, ]
    paths[[i]] <- c(list(lhs = row$lhs, rhs = row$rhs), .block_from(row))
  }

  defined <- pe[pe$op == ":=", ]
  .defined_block <- function(name) {
    row <- defined[defined$lhs == name, ]
    stopifnot(nrow(row) == 1L)
    .block_from(row[1, ])
  }
  effects <- lapply(specs, function(spec) {
    direct <- NULL
    total <- NULL
    if (paste(spec$to, spec$from) %in% edge_set) {
      row <- reg_rows[
        reg_rows$lhs == spec$to & reg_rows$rhs == spec$from,
      ]
      stopifnot(nrow(row) == 1L)
      direct <- .block_from(row[1, ])
      total <- .defined_block(paste0("tot_", spec$id))
    }
    list(
      id = spec$id,
      direct = direct,
      indirect = .defined_block(paste0("ind_", spec$id)),
      total = total
    )
  })
  sums <- lapply(sum_keys, function(key) {
    parts <- strsplit(key, " ")[[1L]]
    block <- .defined_block(paste0("sum_", parts[[1L]], "_", parts[[2L]]))
    c(list(from = parts[[1L]], to = parts[[2L]]), block)
  })

  list(
    bootstrap = list(
      resamples = resamples,
      completed = as.integer(completed),
      ci_level = ci_level,
      ci_type = ci_type
    ),
    paths = paths,
    effects = effects,
    sums = sums
  )
}
