#!/bin/bash
# Hook SessionStart — prépare l'environnement de l'usine à vidéos faceless.
# Installe les prérequis système (ffmpeg, espeak-ng) et les dépendances Python
# afin que la pipeline soit exécutable dès le démarrage d'une session web.
set -euo pipefail

# N'exécuter que dans l'environnement distant (Claude Code on the web).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# --- Prérequis système -------------------------------------------------- #
# Idempotent : on n'installe que ce qui manque. --no-install-recommends évite
# des paquets vaapi cassés dans certaines images.
need_apt=()
command -v ffmpeg   >/dev/null 2>&1 || need_apt+=(ffmpeg)
command -v espeak-ng >/dev/null 2>&1 || need_apt+=(espeak-ng)
if [ "${#need_apt[@]}" -gt 0 ]; then
  apt-get update -y
  apt-get install -y --no-install-recommends "${need_apt[@]}"
fi

# --- Dépendances Python ------------------------------------------------- #
pip3 install --quiet -r requirements.txt

# edge-tts s'appuie sur certifi ; si un proxy d'egress ré-émet le TLS, on
# ajoute son CA au bundle certifi pour que la synthèse vocale fonctionne.
if [ -f /root/.ccr/ca-bundle.crt ]; then
  CERTIFI_PEM="$(python3 -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
  if [ -n "${CERTIFI_PEM:-}" ] && ! grep -q "ccr-agent-proxy" "$CERTIFI_PEM" 2>/dev/null; then
    { echo ""; echo "# ccr-agent-proxy"; cat /root/.ccr/ca-bundle.crt; } >> "$CERTIFI_PEM"
  fi
fi

echo "✓ Environnement prêt : ffmpeg, espeak-ng et dépendances Python installés."
