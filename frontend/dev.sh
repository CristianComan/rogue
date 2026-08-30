#!/bin/bash
# Vite 8/rolldown needs Node 20+ (util.styleText); the OS-level /usr/bin/node
# on this machine is 18.x, so we use the nvm-managed Node instead. Resolves
# via `nvm use default` (see .nvmrc) rather than a hardcoded version path,
# so this doesn't need editing every time the machine's Node gets upgraded.
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1091
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
cd "$(dirname "$0")" || exit 1
nvm use default >/dev/null
exec npm run dev -- --host
