#!/bin/bash
# Start the local computer server so the CUA agent can control your desktop.
# Run this in a separate terminal before running the agent.
DISPLAY=:0 python -m computer_server --log-level debug
