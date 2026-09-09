#!/bin/bash

while true; do
    for i in {1..10}; do
        python3 human-visit-proxy.py yes
    done

    sleep 900
done
