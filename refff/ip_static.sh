sudo nmcli con mod "enp2s0" \
  connection.autoconnect yes \
  connection.interface-name enp2s0 \
  connection.wait-device-timeout 30 \
  connection.autoconnect-priority 100 \
  connection.autoconnect-retries -1
