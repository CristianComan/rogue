#!/bin/bash
# Vite 8/rolldown needs Node 20+ (util.styleText); this repo's system Node is
# 18.x. Prefix PATH with the nvm-installed v20 so every subprocess this
# spawns (npm's script shell, the vite bin's own `env node` shebang) resolves
# the right node, not just this wrapper's direct invocation.
export PATH="/home/cristian/.nvm/versions/node/v20.20.2/bin:$PATH"
cd "$(dirname "$0")" || exit 1
exec npm run dev -- --host
