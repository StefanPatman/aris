#!/bin/bash

benchmarks=(ep cg mg ft)

for a in "${benchmarks[@]}"; do
    for b in "${benchmarks[@]}"; do
        python parse_combined.py -d "$a" "$b" -o "plots/colocation/$a-$b.png"
    done
done
