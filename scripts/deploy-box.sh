#!/bin/bash
# Lay out /tmp/tt-run on a test box from a tarball dropped at /tmp/tt-run.tar.
# Keeps the box's own checkouts untouched: everything lives in scratch and is
# reached through PYTHONPATH.
set -eu
rm -rf /tmp/tt-run
mkdir -p /tmp/tt-run
tar -xf /tmp/tt-run.tar -C /tmp/tt-run
ls /tmp/tt-run
