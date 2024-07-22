#!/bin/bash

# Create a new tmux session
tmux new-session -d -s pino

# Commands to run in new windows
cmd1="cd ~/projects/pino/subscriptions && source venv/bin/activate && python3 server.py"
cmd2="cd ~/projects/pino/scheduled-injest && source venv/bin/activate && python3 schduled-injest.py"
cmd3="cd ~/projects/pino/realtime-injest && source venv/bin/activate && python3 server.py"

# Commands to run docker containers in new windows
cmd4="docker start gotify_gotify_1 && docker attach gotify_gotify_1"
cmd5="docker start nominatim && docker attach nominatim"
cmd6="docker start timescaledb_container && docker attach timescaledb_container"

# Run each command in a new tmux window
tmux new-window -t pino:1 -n "subscriptions" bash -c "$cmd1; exec bash"
tmux new-window -t pino:2 -n "scheduled-injest" bash -c "$cmd2; exec bash"
tmux new-window -t pino:3 -n "realtime-injest" bash -c "$cmd3; exec bash"
tmux new-window -t pino:4 -n "gotify_gotify_1" bash -c "$cmd4; exec bash"
tmux new-window -t pino:5 -n "nominatim" bash -c "$cmd5; exec bash"
tmux new-window -t pino:6 -n "timescaledb_container" bash -c "$cmd6; exec bash"

# Attach to the tmux session
tmux attach-session -t pino

