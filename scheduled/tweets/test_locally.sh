(eval "$(grep -v '^#' ../../.env | sed 's/^/export /')" && python3 injest.py )