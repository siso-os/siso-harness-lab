#!/bin/sh
# Run every phase even when an earlier one fails; never mask a failed phase.
node --test tests/*.test.mjs
node_status=$?
python3 -B -m unittest discover -s tests -p test_audit.py
python_status=$?
[ "$node_status" -eq 0 ] && [ "$python_status" -eq 0 ]
