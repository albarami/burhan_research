# Burhān R assumptions worker (FR-601; PB-05/06; AT-M09-3).
#
# Base-R implementations of the governed diagnostics, written from the
# published formulas (independent of the Python path):
#
# - Mardia (1970) multivariate skewness/kurtosis with the biased
#   (divisor-n) covariance — the psych/MVN convention the known-answer
#   fixture anchors (Korkmaz et al. 2014, The R Journal 6(2):151-162).
# - Univariate skewness and excess kurtosis by population moments.
# - VIF/tolerance across composites: VIF_j = 1 / (1 - R2_j).
# - Mahalanobis D2 on complete cases at the caller-supplied criterion.
#
# Payload: { op: "diagnostics", cells: [[...]], columns: [...],
#            mahalanobis_p } with rows as cases; nulls are missing.

run_worker <- function(payload) {
  op <- payload$op
  if (!identical(op, "diagnostics")) {
    stop("assumptions_worker: unimplemented op '", op, "'")
  }
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
  complete <- data[stats::complete.cases(data), , drop = FALSE]
  n <- nrow(complete)
  p <- ncol(complete)
  stopifnot(n > p, p >= 2L)

  centered <- sweep(complete, 2L, colMeans(complete))
  covariance <- crossprod(centered) / n  # biased, divisor n (Mardia 1970)
  inverse <- solve(covariance)
  gram <- centered %*% inverse %*% t(centered)
  b1p <- sum(gram^3) / n^2
  b2p <- sum(diag(gram)^2) / n
  skew_statistic <- n * b1p / 6
  skew_df <- p * (p + 1) * (p + 2) / 6
  skew_p <- stats::pchisq(skew_statistic, df = skew_df, lower.tail = FALSE)
  kurtosis_z <- (b2p - p * (p + 2)) / sqrt(8 * p * (p + 2) / n)
  kurtosis_p <- 2 * stats::pnorm(abs(kurtosis_z), lower.tail = FALSE)

  univariate <- lapply(seq_len(p), function(column) {
    values <- complete[, column]
    deviations <- values - mean(values)
    m2 <- mean(deviations^2)
    list(
      item = columns[[column]],
      skewness = mean(deviations^3) / m2^1.5,
      kurtosis = mean(deviations^4) / m2^2 - 3
    )
  })

  vif <- lapply(seq_len(p), function(column) {
    response <- complete[, column]
    predictors <- complete[, -column, drop = FALSE]
    fit <- stats::lm.fit(cbind(1, predictors), response)
    residual <- sum(fit$residuals^2)
    total <- sum((response - mean(response))^2)
    r_squared <- if (total > 0) 1 - residual / total else 0
    list(
      composite = columns[[column]],
      vif = if (r_squared >= 1) Inf else 1 / (1 - r_squared)
    )
  })

  d2 <- stats::mahalanobis(complete, colMeans(complete), stats::cov(complete))
  criterion <- stats::qchisq(
    1 - as.numeric(payload$mahalanobis_p),
    df = p
  )

  list(
    mardia = list(
      n = n, p = p, b1p = b1p, skew_statistic = skew_statistic,
      skew_p = skew_p, b2p = b2p, kurtosis_z = kurtosis_z,
      kurtosis_p = kurtosis_p
    ),
    univariate = univariate,
    vif = vif,
    mahalanobis = list(
      criterion_d2 = criterion,
      flagged = sum(d2 > criterion)
    )
  )
}
