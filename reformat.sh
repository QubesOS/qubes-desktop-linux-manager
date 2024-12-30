#!/bin/sh --
# Use bwrap to ensure that a (future) version of black
# never accesses the Internet when it should not.
exec bwrap --unshare-pid \
           --unshare-ipc \
           --unshare-uts \
           --unshare-net \
           --dev-bind / / \
           --tmpfs /tmp \
           --tmpfs /var/tmp \
           --proc /proc \
           --tmpfs /dev/shm \
           -- \
           black -l80 qui/ qubes_config/ stubs/
