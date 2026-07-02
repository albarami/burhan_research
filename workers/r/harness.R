# Burhān R worker harness (AD-02; architecture §6; standards §2).
# Stateless: pure function of call_<id>.input.json -> call_<id>.output.json.
# Asserts renv is synchronized and sets the injected seed BEFORE any
# computation (NFR-102); captures session identity to stderr for the run log.
# Invocation: Rscript harness.R <worker.R> <input.json> <output.json>

args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3L)
worker_path <- args[[1L]]
input_path <- args[[2L]]
output_path <- args[[3L]]
stopifnot(file.exists(worker_path), file.exists(input_path))

# renv assertion before anything else (NFR-102): drift aborts loudly.
renv_status <- renv::status(project = dirname(worker_path))
if (!isTRUE(renv_status$synchronized)) {
  message("RENV_DRIFT: renv status not synchronized for ", dirname(worker_path))
  quit(save = "no", status = 3L)
}

envelope <- jsonlite::fromJSON(input_path, simplifyVector = FALSE)
stopifnot(
  is.list(envelope),
  !is.null(envelope$call_id),
  !is.null(envelope$seed),
  !is.null(envelope$payload)
)

# Session identity to stderr -> captured into the run log (standards §2).
message("harness: ", R.version.string, "; seed=", envelope$seed)

set.seed(as.integer(envelope$seed))

source(worker_path, local = TRUE)
stopifnot(exists("run_worker", inherits = FALSE))

result <- run_worker(envelope$payload)

output <- list(
  call_id = envelope$call_id,
  status = "ok",
  result = result
)
writeLines(
  jsonlite::toJSON(output, auto_unbox = TRUE, digits = NA, null = "null"),
  con = output_path
)
