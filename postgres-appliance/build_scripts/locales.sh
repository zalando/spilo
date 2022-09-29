#!/bin/bash

## ----------------
## Locales routines
## ----------------

set -ex

apt-get update
apt-get -y upgrade
apt-get install -y locales

# Cleanup all locales but en_US.UTF-8 and optionally specified in ADDITIONAL_LOCALES arg
find /usr/share/i18n/charmaps/ -type f ! -name UTF-8.gz -delete

# Prepare find expression for locales
LOCALE_FIND_EXPR=(-type f)
for loc in en_US en_GB $ADDITIONAL_LOCALES "i18n*" iso14651_t1 iso14651_t1_common "translit_*"; do
    LOCALE_FIND_EXPR+=(! -name "$loc")
done
find /usr/share/i18n/locales/ "${LOCALE_FIND_EXPR[@]}" -delete

# Make sure we have the en_US.UTF-8 and all additional locales available
truncate --size 0 /usr/share/i18n/SUPPORTED
for loc in en_US $ADDITIONAL_LOCALES; do
    echo "$loc.UTF-8 UTF-8" >> /usr/share/i18n/SUPPORTED
    localedef -i "$loc" -c -f UTF-8 -A /usr/share/locale/locale.alias "$loc.UTF-8"
done
