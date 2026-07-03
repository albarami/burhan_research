# Burhān R power worker (FR-401; PB-01; AT-M09-1).
#
# Base-R implementation of the MacCallum-Browne-Sugawara (1996) close-fit
# power procedure: lambda = (N-1) * df * rmsea^2; the test rejects past the
# (1-alpha) quantile of the noncentral chi-square under H0, and power is
# the upper tail of the H1 distribution at that critical value.
#
# Payload ops:
# - close_fit: { df, n, rmsea0, rmsea_a, alpha } — every value supplied
#   by the caller from governed sources.
# - montecarlo: { population_model, analysis_model, focal_paths, n,
#   replications, alpha, seed } — simsem over lavaan (E-R3 resolved
#   2026-07-03: renv extended with the docs/04 governed stack). The
#   population syntax carries exact standardized values from the PB-01
#   montecarlo_population criterion; the seed makes runs bit-reproducible
#   (NFR-101). An unknown op aborts loudly.

run_worker <- function(payload) {
  op <- payload$op
  if (identical(op, "close_fit")) {
    df <- as.integer(payload$df)
    n <- as.integer(payload$n)
    rmsea0 <- as.numeric(payload$rmsea0)
    rmsea_a <- as.numeric(payload$rmsea_a)
    alpha <- as.numeric(payload$alpha)
    stopifnot(df >= 1L, n >= 2L, rmsea0 > 0, rmsea_a > rmsea0)
    lambda0 <- (n - 1) * df * rmsea0^2
    lambda_a <- (n - 1) * df * rmsea_a^2
    critical <- stats::qchisq(1 - alpha, df = df, ncp = lambda0)
    power <- stats::pchisq(
      critical, df = df, ncp = lambda_a, lower.tail = FALSE
    )
    return(list(
      power = power,
      critical = critical,
      lambda0 = lambda0,
      lambda_a = lambda_a
    ))
  }
  if (identical(op, "montecarlo")) {
    # simsem resolves lavaanfun by name on the search path: lavaan (and
    # simsem itself) must be ATTACHED, not merely loaded as namespaces.
    suppressPackageStartupMessages({
      library(lavaan) # nolint: object_usage_linter.
      library(simsem) # nolint: object_usage_linter.
    })
    replications <- as.integer(payload$replications)
    n <- as.integer(payload$n)
    stopifnot(replications >= 2L, n >= 10L)
    output <- simsem::sim(
      nRep = replications,
      model = payload$analysis_model,
      n = n,
      generate = payload$population_model,
      lavaanfun = "sem",
      seed = as.integer(payload$seed),
      silent = TRUE
    )
    power_table <- simsem::getPower(output, alpha = as.numeric(payload$alpha))
    power_names <- rownames(power_table)
    if (is.null(power_names)) power_names <- names(power_table)
    power_values <- as.numeric(power_table)
    focal <- unlist(payload$focal_paths)
    selected <- match(focal, power_names)
    stopifnot(!anyNA(selected))
    power <- as.list(stats::setNames(power_values[selected], focal))
    # No catch-and-continue (standards: guarded statistical layers): the
    # convergence vector must exist and be well-formed, else abort loudly
    # so the harness raises a typed halt.
    convergence_codes <- methods::slot(output, "converged")
    if (!is.numeric(convergence_codes) ||
          length(convergence_codes) != replications) {
      stop(
        "power_worker: simsem output lacks a valid converged vector (",
        "length ", length(convergence_codes), " for ", replications,
        " replications)"
      )
    }
    converged <- sum(convergence_codes == 0L)
    return(list(power = power, converged = converged))
  }
  stop("power_worker: unimplemented op '", op, "'")
}
