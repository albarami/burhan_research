# Burhān echo worker — the trivial TC-04 fixture proving the call contract.
# Returns the payload unchanged plus one deterministic draw from the
# injected seed (the harness has already called set.seed), demonstrating
# seed plumbing end to end (AT-M04-5).

run_worker <- function(payload) {
  list(
    echo = payload,
    draw = stats::runif(1L)
  )
}
