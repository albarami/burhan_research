# Burhān R structural worker (FR-801/803; PB-15/16; AT-M11-1/5).
#
# op "sem": { cells, columns, constructs: [{code, indicators}],
#   second_order: {code, components} | null, approach, carrier, regressions:
#   [{lhs, rhs}] } — regressions come from the contract's direct hypotheses.
#
# Carrier semantics (FR-803):
# - null / "full_hierarchy": one lavaan::sem over the full latent hierarchy
#   (first-order measurement, second-order line when declared) plus the
#   structural regressions.
# - "latent_scores": stage-1 correlated first-order CFA -> lavPredict scores;
#   the second-order construct's score comes from a stage-2 CFA on its
#   component scores; the structural model is then an observed-variable
#   path model over the score columns.
#
# Fit is REPORTED only: nothing in this worker consults a fit result to
# change the model (PB-15 failure_action = report). Malformed inputs and
# non-converged fits abort loudly.

.structural_data <- function(payload) {
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

.first_order_syntax <- function(constructs) {
  lines <- vapply(constructs, function(construct) {
    paste0(
      construct$code, " =~ ",
      paste(unlist(construct$indicators), collapse = " + ")
    )
  }, character(1L))
  paste(lines, collapse = "\n")
}

.regression_syntax <- function(regressions) {
  lhs_all <- vapply(regressions, function(r) r$lhs, character(1L))
  lines <- vapply(unique(lhs_all), function(lhs) {
    rhs <- unlist(lapply(regressions, function(r) {
      if (identical(r$lhs, lhs)) r$rhs else NULL
    }))
    paste0(lhs, " ~ ", paste(rhs, collapse = " + "))
  }, character(1L))
  paste(lines, collapse = "\n")
}

.fit_block <- function(fit) {
  measures <- lavaan::fitMeasures(
    fit,
    c(
      "chisq", "df", "pvalue", "cfi", "tli", "rmsea",
      "rmsea.ci.lower", "rmsea.ci.upper", "srmr"
    )
  )
  pvalue <- measures[["pvalue"]]
  list(
    chisq = as.numeric(measures[["chisq"]]),
    df = as.integer(measures[["df"]]),
    pvalue = if (is.na(pvalue)) NULL else as.numeric(pvalue),
    cfi = as.numeric(measures[["cfi"]]),
    tli = as.numeric(measures[["tli"]]),
    rmsea = as.numeric(measures[["rmsea"]]),
    rmsea_ci_lower = as.numeric(measures[["rmsea.ci.lower"]]),
    rmsea_ci_upper = as.numeric(measures[["rmsea.ci.upper"]]),
    srmr = as.numeric(measures[["srmr"]])
  )
}

.path_rows <- function(fit) {
  est <- lavaan::parameterEstimates(fit)
  std <- lavaan::standardizedSolution(fit)
  est <- est[est$op == "~", ]
  std <- std[std$op == "~", ]
  rows <- vector("list", nrow(est))
  for (i in seq_len(nrow(est))) {
    p_value <- est$pvalue[[i]]
    rows[[i]] <- list(
      lhs = est$lhs[[i]],
      rhs = est$rhs[[i]],
      est = est$est[[i]],
      std = std$est.std[[i]],
      se = est$se[[i]],
      p = if (is.na(p_value)) NULL else p_value
    )
  }
  rows
}

run_worker <- function(payload) {
  stopifnot(identical(payload$op, "sem"))
  data <- .structural_data(payload)
  constructs <- payload$constructs
  second <- payload$second_order
  carrier <- payload$carrier
  regressions <- payload$regressions
  stopifnot(length(constructs) >= 1L, length(regressions) >= 1L)
  first_syntax <- .first_order_syntax(constructs)
  reg_syntax <- .regression_syntax(regressions)

  if (is.null(carrier) || identical(carrier, "full_hierarchy")) {
    parts <- first_syntax
    if (!is.null(second)) {
      parts <- paste0(
        parts, "\n", second$code, " =~ ",
        paste(unlist(second$components), collapse = " + ")
      )
    }
    syntax <- paste0(parts, "\n", reg_syntax)
    fit <- lavaan::sem(syntax, data = data, meanstructure = TRUE)
  } else if (identical(carrier, "latent_scores")) {
    stopifnot(!is.null(second))
    stage1 <- lavaan::cfa(first_syntax, data = data, std.lv = TRUE)
    stopifnot(isTRUE(lavaan::lavInspect(stage1, "converged")))
    scores <- as.data.frame(lavaan::lavPredict(stage1))
    so_syntax <- paste0(
      second$code, " =~ ",
      paste(unlist(second$components), collapse = " + ")
    )
    stage2 <- lavaan::cfa(so_syntax, data = scores)
    stopifnot(isTRUE(lavaan::lavInspect(stage2, "converged")))
    scores[[second$code]] <- as.numeric(lavaan::lavPredict(stage2))
    syntax <- reg_syntax
    fit <- lavaan::sem(syntax, data = scores, meanstructure = TRUE)
  } else {
    stop("structural_worker: unknown carrier '", carrier, "'")
  }
  stopifnot(isTRUE(lavaan::lavInspect(fit, "converged")))
  list(
    carrier = carrier,
    model = list(
      syntax = syntax,
      nfree = as.integer(lavaan::lavInspect(fit, "npar"))
    ),
    fit = .fit_block(fit),
    paths = .path_rows(fit)
  )
}
