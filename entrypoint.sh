#!/bin/bash

set -e

shopt -s extglob

if ! getent passwd "$APP_NAME" >/dev/null; then
    PUID=${PUID:-9001}
    PGID=${PGID:-9001}
    echo "Creating user 'evaluate' with UID $PUID and GID $PGID..."
    groupadd -og "$PGID" "$APP_NAME"
    useradd -ou "$PUID" -g "$APP_NAME" -Md "/$APP_NAME" -K UID_MIN=0 "$APP_NAME"

    chown "$APP_NAME":"$APP_NAME" "/$APP_NAME" "/$APP_NAME/results"
    chown -R "$APP_NAME":"$APP_NAME" "/$APP_NAME/"!(entrypoint.sh|results) "$LINUX_KSRC_PATH"
fi

exec gosu "$APP_NAME" "$@"
