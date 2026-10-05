#!/bin/sh
set -eu

umask 077
if [ ! -s /mosquitto/data/passwordfile ]; then
  printf '%s\n%s\n' "$DEV_MQTT_PASSWORD" "$DEV_MQTT_PASSWORD" \
    | mosquitto_passwd -c /mosquitto/data/passwordfile "$DEV_MQTT_USER"
  chown mosquitto:mosquitto /mosquitto/data/passwordfile
fi
exec mosquitto -c /mosquitto/config/mosquitto.conf
