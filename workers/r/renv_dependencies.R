# renv dependency declarations (E-R3, researcher-authorized 2026-07-03).
#
# renv's implicit snapshot records packages referenced by project code;
# this file declares the docs/04 §4 governed stats stack so the lockfile
# pins it even before every worker references every package. Never
# sourced by the harness. (MVN and car remain blocked on system
# libraries — libcurl/GSL/nlopt dev headers — and join when the
# researcher installs those; mice and arrow stay deferred per E-R3.)

library(jsonlite)
library(lavaan)
library(semTools)
library(simsem)
library(psych)
