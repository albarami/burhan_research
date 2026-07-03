# Burhān R power worker (FR-401; PB-01; AT-M09-1).
#
# Base-R implementation of the MacCallum-Browne-Sugawara (1996) close-fit
# power procedure: lambda = (N-1) * df * rmsea^2; the test rejects past the
# (1-alpha) quantile of the noncentral chi-square under H0, and power is
# the upper tail of the H1 distribution at that critical value.
#
# Payload: { op: "close_fit", df, n, rmsea0, rmsea_a, alpha } — every value
# supplied by the caller from governed sources.
#
# The Monte Carlo op (PB-01, simsem) is NOT implemented here: the governed
# R stack (04: lavaan/semTools/simsem) is not yet in workers/r/renv.lock
# (escalation E-R3); this worker ships no placeholder statistics. An
# unknown or unimplemented op aborts loudly.

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
  stop("power_worker: unimplemented op '", op,
       "' (montecarlo awaits the governed R stack; escalation E-R3)")
}
