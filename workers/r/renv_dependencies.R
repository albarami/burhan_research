# renv dependency declarations (E-R3, researcher-authorized 2026-07-03).
#
# renv's implicit snapshot records packages referenced by project code;
# this file declares the full docs/04 §4 governed stats stack so the
# lockfile pins it even before every worker references every package.
# Never sourced by the harness. (mice and arrow stay deferred per E-R3
# until a contract requires them.)

library(jsonlite)
library(lavaan)
library(semTools)
library(simsem)
library(psych)
library(MVN)
library(car)
