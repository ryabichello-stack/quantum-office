#!/usr/bin/env bash
# Deploy dlno.ru as primary marketing domain (root site, no /delno prefix).
# Delegates to install_dlno_ingress.sh for full subdomain routing.
set -euo pipefail
exec "$(dirname "$0")/install_dlno_ingress.sh" "$@"
