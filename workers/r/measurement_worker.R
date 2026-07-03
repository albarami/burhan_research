# Burhān R measurement worker (FR-701–704; PB-08–PB-12; AT-M10-1/2/3).
#
# lavaan is the authoritative engine; semTools supplies the reference
# reliability/HTMT computations (both renv-locked). Ops:
#
# - cfa: { cells, columns, constructs: [{code, indicators}],
#   second_order: {code, components} | null,
#   approach: "repeated_indicator" | "two_stage" }
#   Returns first_order {loadings, reliability}, second_order (when
#   declared) {loadings, reliability, stage}, fit, validity
#   {latent_correlations, htmt}. Two-stage: stage 1 is the correlated
#   first-order CFA; stage 2 fits the higher-order factor on lavPredict
#   factor scores.
#   Level-2 reliability for the repeated-indicator fit comes from the
#   reference implementation semTools::reliabilityL2 (renv-locked):
#   cr_l2 = omegaL2 (reliability of the first-order-factor composite as
#   a measure of the L2 factor), omega_l1 = omegaL1 (share of the total
#   item-composite variance carried by the L2 factor). The AT-M10-1
#   benchmark pins both against captured semTools values.
#
# - cmb: same data payload. Harman screen: first principal component's
#   share of total standardized variance (Podsakoff et al. 2003
#   convention). Substantive test: CFA with vs without an orthogonal
#   common latent factor (equality-constrained CLF loadings for
#   identification); returns the CLF method-variance share (mean
#   standardized lambda_CLF^2) and per-item standardized loading
#   distortions.
#
# No placeholder statistics; malformed inputs abort loudly.

.measurement_data <- function(payload) {
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

.loading_rows <- function(fit, ops, lhs_name, rhs_name) {
  est <- lavaan::parameterEstimates(fit)
  std <- lavaan::standardizedSolution(fit)
  keep <- est$op == "=~" & est$lhs %in% ops
  est <- est[keep, ]
  std <- std[std$op == "=~" & std$lhs %in% ops, ]
  rows <- vector("list", nrow(est))
  for (i in seq_len(nrow(est))) {
    rows[[i]] <- stats::setNames(
      list(
        est$lhs[[i]], est$rhs[[i]], est$est[[i]], std$est.std[[i]],
        est$se[[i]],
        if (is.na(est$pvalue[[i]])) NULL else est$pvalue[[i]]
      ),
      c(lhs_name, rhs_name, "est", "std", "se", "p")
    )
  }
  rows
}

.first_order_reliability <- function(fit, constructs) {
  codes <- vapply(constructs, function(c) c$code, character(1L))
  cr <- semTools::compRelSEM(fit)
  alpha <- semTools::compRelSEM(fit, tau.eq = TRUE)
  ave <- semTools::AVE(fit)
  lapply(codes, function(code) {
    list(
      construct = code,
      alpha = as.numeric(alpha[[code]]),
      cr = as.numeric(cr[[code]]),
      ave = as.numeric(ave[[code]])
    )
  })
}

.fit_block <- function(fit) {
  measures <- lavaan::fitMeasures(
    fit, c("chisq", "df", "pvalue", "cfi", "tli", "rmsea", "srmr")
  )
  list(
    chisq = as.numeric(measures[["chisq"]]),
    df = as.integer(measures[["df"]]),
    pvalue = as.numeric(measures[["pvalue"]]),
    cfi = as.numeric(measures[["cfi"]]),
    tli = as.numeric(measures[["tli"]]),
    rmsea = as.numeric(measures[["rmsea"]]),
    srmr = as.numeric(measures[["srmr"]])
  )
}

.level2_reliability <- function(fit, so_code) {
  # Reference implementation (deprecated upstream, stable in the
  # renv-locked semTools; suppressed warning is the deprecation notice).
  values <- suppressWarnings(semTools::reliabilityL2(fit, so_code))
  omega_l1 <- as.numeric(values[["omegaL1"]])
  cr_l2 <- as.numeric(values[["omegaL2"]])
  stopifnot(is.finite(omega_l1), is.finite(cr_l2))
  list(construct = so_code, cr_l2 = cr_l2, omega_l1 = omega_l1)
}

.validity_block <- function(first_order_fit, first_syntax, data, constructs) {
  codes <- vapply(constructs, function(c) c$code, character(1L))
  corr <- lavaan::lavInspect(first_order_fit, "cor.lv")
  pairs <- list()
  if (length(codes) >= 2L) {
    index <- 1L
    for (a in seq_along(codes)) {
      for (b in seq_along(codes)) {
        if (a < b) {
          pairs[[index]] <- list(
            a = codes[[a]], b = codes[[b]],
            value = as.numeric(corr[codes[[a]], codes[[b]]])
          )
          index <- index + 1L
        }
      }
    }
  }
  htmt_pairs <- list()
  if (length(codes) >= 2L) {
    htmt <- semTools::htmt(first_syntax, data = data)
    index <- 1L
    for (a in seq_along(codes)) {
      for (b in seq_along(codes)) {
        if (a < b) {
          htmt_pairs[[index]] <- list(
            a = codes[[a]], b = codes[[b]],
            value = as.numeric(htmt[codes[[b]], codes[[a]]])
          )
          index <- index + 1L
        }
      }
    }
  }
  list(latent_correlations = pairs, htmt = htmt_pairs)
}

run_worker <- function(payload) {
  op <- payload$op
  data <- .measurement_data(payload)
  constructs <- payload$constructs
  codes <- vapply(constructs, function(c) c$code, character(1L))
  first_syntax <- .first_order_syntax(constructs)

  if (identical(op, "cfa")) {
    approach <- payload$approach
    second <- payload$second_order
    if (is.null(second)) {
      fit <- lavaan::cfa(first_syntax, data = data, std.lv = TRUE)
      return(list(
        approach = "first_order_only",
        first_order = list(
          loadings = .loading_rows(fit, codes, "construct", "item"),
          reliability = .first_order_reliability(fit, constructs)
        ),
        second_order = NULL,
        fit = .fit_block(fit),
        validity = .validity_block(fit, first_syntax, data, constructs)
      ))
    }
    so_code <- second$code
    components <- unlist(second$components)
    if (identical(approach, "repeated_indicator")) {
      syntax <- paste0(
        first_syntax, "\n", so_code, " =~ ",
        paste(components, collapse = " + ")
      )
      fit <- lavaan::cfa(syntax, data = data, meanstructure = TRUE)
      first_fit <- lavaan::cfa(first_syntax, data = data, std.lv = TRUE)
      return(list(
        approach = "repeated_indicator",
        first_order = list(
          loadings = .loading_rows(fit, codes, "construct", "item"),
          reliability = .first_order_reliability(first_fit, constructs)
        ),
        second_order = list(
          loadings = .loading_rows(fit, so_code, "construct", "component"),
          reliability = .level2_reliability(fit, so_code),
          stage = 1L
        ),
        fit = .fit_block(fit),
        validity = .validity_block(first_fit, first_syntax, data, constructs)
      ))
    }
    if (identical(approach, "two_stage")) {
      stage1 <- lavaan::cfa(first_syntax, data = data, std.lv = TRUE)
      scores <- as.data.frame(lavaan::lavPredict(stage1))
      stage2_syntax <- paste0(
        so_code, " =~ ", paste(components, collapse = " + ")
      )
      stage2 <- lavaan::cfa(stage2_syntax, data = scores)
      l2_std <- lavaan::standardizedSolution(stage2)
      l2_rows <- .loading_rows(stage2, so_code, "construct", "component")
      lambda2 <- l2_std[l2_std$op == "=~", "est.std"]
      resid2 <- l2_std[l2_std$op == "~~" & l2_std$lhs == l2_std$rhs &
                         l2_std$lhs != so_code, "est.std"]
      cr_l2 <- sum(lambda2)^2 / (sum(lambda2)^2 + sum(resid2))
      return(list(
        approach = "two_stage",
        first_order = list(
          loadings = .loading_rows(stage1, codes, "construct", "item"),
          reliability = .first_order_reliability(stage1, constructs)
        ),
        second_order = list(
          loadings = l2_rows,
          reliability = list(
            construct = so_code, cr_l2 = cr_l2, omega_l1 = cr_l2
          ),
          stage = 2L
        ),
        fit = .fit_block(stage1),
        validity = .validity_block(stage1, first_syntax, data, constructs)
      ))
    }
    stop("measurement_worker: unknown higher-order approach '", approach, "'")
  }

  if (identical(op, "cmb")) {
    items <- unlist(lapply(constructs, function(c) c$indicators))
    substantive <- data[, items, drop = FALSE]
    correlation <- stats::cor(substantive)
    eigenvalues <- eigen(
      correlation, symmetric = TRUE, only.values = TRUE
    )$values
    harman_share <- eigenvalues[[1L]] / ncol(substantive)

    base_fit <- lavaan::cfa(first_syntax, data = data, std.lv = TRUE)
    base_std <- lavaan::standardizedSolution(base_fit)
    base_loadings <- base_std[base_std$op == "=~", c("lhs", "rhs", "est.std")]

    # Marker-anchored CLF (Williams et al. 2010): method-only markers
    # identify the common latent factor; without them a uniform CLF is
    # near-equivalent to inflated trait loadings plus correlation.
    markers <- unlist(payload$marker_items)
    stopifnot(length(markers) >= 1L)
    clf_indicators <- c(markers, items)
    clf_syntax <- paste0(
      first_syntax, "\n",
      "CLF =~ ", paste(clf_indicators, collapse = " + ")
    )
    orthogonal <- paste(
      vapply(codes, function(code) paste0("CLF ~~ 0*", code), character(1L)),
      collapse = "\n"
    )
    clf_fit <- lavaan::cfa(
      paste(clf_syntax, orthogonal, sep = "\n"),
      data = data, std.lv = TRUE
    )
    clf_std <- lavaan::standardizedSolution(clf_fit)
    clf_method <- clf_std[clf_std$op == "=~" & clf_std$lhs == "CLF" &
                            clf_std$rhs %in% items, ]
    method_share <- mean(clf_method$est.std^2)
    clf_trait <- clf_std[clf_std$op == "=~" & clf_std$lhs %in% codes,
                         c("lhs", "rhs", "est.std")]
    distortions <- list()
    for (i in seq_len(nrow(base_loadings))) {
      construct <- base_loadings$lhs[[i]]
      item <- base_loadings$rhs[[i]]
      with_clf <- clf_trait[clf_trait$lhs == construct &
                              clf_trait$rhs == item, "est.std"]
      distortions[[i]] <- list(
        construct = construct,
        item = item,
        without_clf = base_loadings$est.std[[i]],
        with_clf = as.numeric(with_clf),
        abs_delta = abs(base_loadings$est.std[[i]] - as.numeric(with_clf))
      )
    }
    return(list(
      harman = list(single_factor_share = harman_share),
      clf = list(
        method_variance_share = method_share,
        loading_distortions = distortions
      )
    ))
  }

  stop("measurement_worker: unimplemented op '", op, "'")
}
