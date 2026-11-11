#!/usr/bin/env bash

set -Eeuo pipefail

#######################################
# Configurações padrão
#######################################
AUTO_CONFIRM=false
DO_PUSH=true
TARGET_BRANCH=""
TARGET_REMOTE="origin"
CUSTOM_MESSAGE=""
OPEN_EDITOR=false

#######################################
# Cores
#######################################
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  CYAN='\033[0;36m'
  NC='\033[0m'
else
  RED=''
  GREEN=''
  YELLOW=''
  BLUE=''
  CYAN=''
  NC=''
fi

#######################################
# Funções de log
#######################################
log() {
  printf "%b[INFO]%b %s\n" "${BLUE}" "${NC}" "$*"
}

ok() {
  printf "%b[OK]%b %s\n" "${GREEN}" "${NC}" "$*"
}

warn() {
  printf "%b[WARN]%b %s\n" "${YELLOW}" "${NC}" "$*"
}

err() {
  printf "%b[ERRO]%b %s\n" "${RED}" "${NC}" "$*" >&2
}

die() {
  err "$*"
  exit 1
}

#######################################
# Ajuda
#######################################
usage() {
  cat <<'EOF'
Uso:
  ./git-smart-update.sh [opções]

Opções:
  --yes, -y             Executa sem pedir confirmação
  --no-push             Não executa git push
  --branch <nome>       Define branch alvo
  --remote <nome>       Define remoto (padrão: origin)
  --msg [mensagem]      Usa mensagem customizada ou abre editor
  --edit                Permite editar a mensagem antes do commit
  --help, -h            Exibe ajuda

Exemplos:
  ./git-smart-update.sh
  ./git-smart-update.sh --yes
  ./git-smart-update.sh --no-push
  ./git-smart-update.sh --branch main --remote origin
  ./git-smart-update.sh --msg "feat(core): ajusta fluxo de sync"
  ./git-smart-update.sh --msg
  ./git-smart-update.sh --msg ""
  ./git-smart-update.sh --edit

Editores suportados:
  nano, vim, vi, code --wait

Prioridade:
  VISUAL > EDITOR > nano > vim > vi
EOF
}

#######################################
# Utilidades
#######################################
confirm() {
  local prompt="${1:-Deseja continuar?}"

  if [[ "${AUTO_CONFIRM}" == "true" ]]; then
    return 0
  fi

  read -r -p "${prompt} [s/N]: " ans
  [[ "${ans,,}" =~ ^(s|sim|y|yes)$ ]]
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Comando obrigatório não encontrado: $1"
}

is_git_repo() {
  git rev-parse --is-inside-work-tree >/dev/null 2>&1
}

get_current_branch() {
  git rev-parse --abbrev-ref HEAD
}

has_any_local_changes() {
  [[ -n "$(git status --porcelain)" ]]
}

has_staged_changes() {
  [[ -n "$(git diff --cached --name-only)" ]]
}

join_by_comma() {
  paste -sd ", " -
}

trim_empty_lines() {
  sed '/^[[:space:]]*$/d'
}

#######################################
# Editor
#######################################
open_message_editor() {
  local file="$1"
  local editor_command="${VISUAL:-${EDITOR:-nano}}"

  if ! command -v "${editor_command%% *}" >/dev/null 2>&1; then
    if command -v nano >/dev/null 2>&1; then
      editor_command="nano"
    elif command -v vim >/dev/null 2>&1; then
      editor_command="vim"
    elif command -v vi >/dev/null 2>&1; then
      editor_command="vi"
    else
      die "Nenhum editor encontrado. Instale nano, vim ou vi."
    fi
  fi

  log "Abrindo editor: ${editor_command}"

  # Permite utilizar editores com argumentos, como code --wait.
  # shellcheck disable=SC2086
  ${editor_command} "${file}" || die "Não foi possível editar a mensagem."
}

#######################################
# Parse de argumentos
#######################################
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y)
      AUTO_CONFIRM=true
      shift
      ;;

    --no-push)
      DO_PUSH=false
      shift
      ;;

    --branch)
      [[ $# -ge 2 && -n "$2" ]] || die "Faltou valor para --branch"
      TARGET_BRANCH="$2"
      shift 2
      ;;

    --remote)
      [[ $# -ge 2 && -n "$2" ]] || die "Faltou valor para --remote"
      TARGET_REMOTE="$2"
      shift 2
      ;;

    --msg)
      shift

      if [[ $# -gt 0 && "$1" != -* ]]; then
        CUSTOM_MESSAGE="$1"
        shift
      else
        OPEN_EDITOR=true
      fi
      ;;

    --edit)
      OPEN_EDITOR=true
      shift
      ;;

    --help|-h)
      usage
      exit 0
      ;;

    *)
      die "Opção inválida: $1"
      ;;
  esac
done

#######################################
# Validações iniciais
#######################################
require_cmd git

is_git_repo || die "Este diretório não é um repositório Git."

CURRENT_BRANCH="$(get_current_branch)"

[[ -n "${TARGET_BRANCH}" ]] || TARGET_BRANCH="${CURRENT_BRANCH}"

git remote get-url "${TARGET_REMOTE}" >/dev/null 2>&1 \
  || die "Remoto '${TARGET_REMOTE}' não encontrado."

#######################################
# Funções de análise das mudanças
#######################################
collect_changed_files() {
  {
    git diff --cached --name-only || true
    git diff --name-only || true
    git ls-files --others --exclude-standard || true
  } | sed '/^$/d' | sort -u
}

collect_status_porcelain() {
  git status --porcelain || true
}

guess_commit_type() {
  local files="$1"

  if printf "%s\n" "${files}" | grep -Eiq '(^|/)(docs|doc)/|README|\.md$|\.rst$|\.adoc$|\.txt$'; then
    echo "docs"
    return
  fi

  if printf "%s\n" "${files}" | grep -Eiq '(^|/)(test|tests|spec|specs|__tests__)/|(_test\.|\.spec\.)'; then
    echo "test"
    return
  fi

  if printf "%s\n" "${files}" | grep -Eiq 'Dockerfile|docker-compose|\.github/|Makefile|Jenkinsfile|\.gitlab-ci|helm/|k8s/|terraform|ansible|nginx|traefik'; then
    echo "chore"
    return
  fi

  if printf "%s\n" "${files}" | grep -Eiq 'fix|bug|hotfix|correc|ajuste'; then
    echo "fix"
    return
  fi

  echo "feat"
}

guess_scope() {
  local files="$1"

  local first_scope

  first_scope="$(
    printf "%s\n" "${files}" |
      awk -F/ '
        NF==1 { print "repo"; next }
        { print $1 }
      ' |
      sed '/^$/d' |
      sort |
      uniq -c |
      sort -rn |
      head -n1 |
      awk '{print $2}'
  )"

  [[ -n "${first_scope}" ]] || first_scope="repo"

  case "${first_scope}" in
    src|app|api|backend|server) echo "core" ;;
    web|frontend|ui|client) echo "ui" ;;
    docs|doc) echo "docs" ;;
    tests|test|spec|specs) echo "tests" ;;
    infra|deploy|helm|k8s|terraform) echo "infra" ;;
    *) echo "${first_scope}" ;;
  esac
}

guess_action_text() {
  local num_files="$1"
  local added="$2"
  local modified="$3"
  local deleted="$4"
  local renamed="$5"

  if (( deleted > 0 && modified == 0 && added == 0 )); then
    echo "remove arquivos obsoletos"
    return
  fi

  if (( renamed > 0 && modified == 0 && added == 0 )); then
    echo "renomeia arquivos do projeto"
    return
  fi

  if (( num_files == 1 )); then
    echo "ajusta arquivo específico"
    return
  fi

  if (( added > modified )); then
    echo "adiciona novos arquivos e ajustes"
    return
  fi

  if (( modified > 0 )); then
    echo "atualiza arquivos do projeto"
    return
  fi

  echo "atualiza estrutura do repositório"
}

generate_commit_message() {
  local files="$1"
  local status="$2"

  local num_files added modified deleted renamed untracked

  num_files="$(printf "%s\n" "${files}" | sed '/^$/d' | wc -l | tr -d ' ')"

  added="$(printf "%s\n" "${status}" | grep -Ec '^(A |M  |AM|R |C )' || true)"
  modified="$(printf "%s\n" "${status}" | grep -Ec '^ M|^M |^MM|^AM|^RM' || true)"
  deleted="$(printf "%s\n" "${status}" | grep -Ec '^(D | D|MD|DM)' || true)"
  renamed="$(printf "%s\n" "${status}" | grep -Ec '^(R|RM|RD)' || true)"
  untracked="$(printf "%s\n" "${status}" | grep -Ec '^\?\?' || true)"

  local top_dirs

  top_dirs="$(
    printf "%s\n" "${files}" |
      awk -F/ '
        NF==1 { print "repo"; next }
        { print $1 }
      ' |
      sed '/^$/d' |
      sort |
      uniq -c |
      sort -rn |
      head -5 |
      awk '{print $2}'
  )"

  local top_dirs_human
  top_dirs_human="$(printf "%s\n" "${top_dirs}" | sed '/^$/d' | join_by_comma)"
  [[ -n "${top_dirs_human}" ]] || top_dirs_human="repo"

  local ext_summary

  ext_summary="$(
    printf "%s\n" "${files}" |
      awk -F. '
        NF < 2 { print "[sem-ext]"; next }
        { print tolower($NF) }
      ' |
      sed '/^$/d' |
      sort |
      uniq -c |
      sort -rn |
      head -5 |
      awk '{print $2}'
  )"

  local ext_human
  ext_human="$(printf "%s\n" "${ext_summary}" | sed '/^$/d' | join_by_comma)"
  [[ -n "${ext_human}" ]] || ext_human="diversos"

  local commit_type scope action

  commit_type="$(guess_commit_type "${files}")"
  scope="$(guess_scope "${files}")"
  action="$(guess_action_text "${num_files}" "${added}" "${modified}" "${deleted}" "${renamed}")"

  cat <<EOF
${commit_type}(${scope}): ${action}

Arquivos alterados: ${num_files}
Pastas impactadas: ${top_dirs_human}
Tipos de arquivo: ${ext_human}
Resumo: ${added} adicionados, ${modified} modificados, ${deleted} removidos, ${renamed} renomeados, ${untracked} não rastreados
EOF
}

#######################################
# Início
#######################################
echo

log "Repositório detectado."
log "Branch atual: ${CURRENT_BRANCH}"
log "Branch alvo: ${TARGET_BRANCH}"
log "Remoto: ${TARGET_REMOTE}"

echo

log "Status atual:"
git status --short || true

echo

#######################################
# Detecta alterações locais
#######################################
STATUS_PORCELAIN="$(collect_status_porcelain)"
CHANGED_FILES="$(collect_changed_files)"

HAS_LOCAL_CHANGES=false

if has_any_local_changes; then
  HAS_LOCAL_CHANGES=true
fi

#######################################
# Gera mensagem de commit
#######################################
COMMIT_MESSAGE=""

if [[ "${HAS_LOCAL_CHANGES}" == "true" ]]; then

  if [[ -n "${CUSTOM_MESSAGE}" ]]; then
    COMMIT_MESSAGE="${CUSTOM_MESSAGE}"

  elif [[ "${OPEN_EDITOR}" != "true" ]]; then
    COMMIT_MESSAGE="$(generate_commit_message "${CHANGED_FILES}" "${STATUS_PORCELAIN}")"
  fi

  if [[ -n "${COMMIT_MESSAGE}" ]]; then
    log "Mensagem sugerida:"
    echo "------------------------------------------------------------"
    printf "%s\n" "${COMMIT_MESSAGE}"
    echo "------------------------------------------------------------"
    echo
  fi

  if [[ "${OPEN_EDITOR}" == "true" ]] || {
    [[ "${AUTO_CONFIRM}" != "true" ]] &&
      confirm "Deseja editar a mensagem do commit?"
  }; then

    TMP_FILE="$(mktemp)"

    trap 'rm -f "${TMP_FILE:-}"' EXIT

    if [[ -n "${COMMIT_MESSAGE}" ]]; then
      printf "%s\n" "${COMMIT_MESSAGE}" > "${TMP_FILE}"
    fi

    open_message_editor "${TMP_FILE}"

    COMMIT_MESSAGE="$(cat "${TMP_FILE}")"

    [[ -n "$(printf "%s" "${COMMIT_MESSAGE}" | tr -d '[:space:]')" ]] \
      || die "A mensagem do commit ficou vazia."

    rm -f "${TMP_FILE}"
    trap - EXIT

    ok "Mensagem de commit capturada."
  fi

fi

#######################################
# Stage + commit antes do pull
#######################################
if [[ "${HAS_LOCAL_CHANGES}" == "true" ]]; then

  if confirm "Deseja adicionar todas as alterações com git add -A?"; then
    git add -A
    ok "Alterações adicionadas ao stage."
  else
    die "Processo cancelado."
  fi

  if has_staged_changes; then

    if confirm "Deseja criar o commit agora?"; then

      COMMIT_SUBJECT="$(printf '%s\n' "${COMMIT_MESSAGE}" | head -n1)"
      COMMIT_BODY="$(printf '%s\n' "${COMMIT_MESSAGE}" | tail -n +2 | trim_empty_lines)"

      if [[ -n "${COMMIT_SUBJECT//[[:space:]]/}" ]]; then
        if [[ -n "${COMMIT_BODY}" ]]; then
          git commit -m "${COMMIT_SUBJECT}" -m "${COMMIT_BODY}"
        else
          git commit -m "${COMMIT_SUBJECT}"
        fi
      else
        die "A mensagem do commit está vazia."
      fi

      ok "Commit criado com sucesso."

    else
      die "Commit cancelado. O pull --rebase não será executado."
    fi

  else
    warn "Após git add -A não houve alterações staged."
  fi

else
  warn "Nenhuma alteração local detectada. Seguindo para atualização da branch."
fi

#######################################
# Fetch
#######################################
echo

log "Buscando atualizações do remoto..."

git fetch "${TARGET_REMOTE}" --prune

ok "Fetch concluído."

#######################################
# Pull --rebase
#######################################
if [[ "${CURRENT_BRANCH}" != "${TARGET_BRANCH}" ]]; then
  warn "Você está na branch '${CURRENT_BRANCH}', mas o alvo configurado é '${TARGET_BRANCH}'."
  warn "O pull será feito na branch atual."
fi

if confirm "Deseja executar git pull --rebase agora?"; then

  git pull --rebase "${TARGET_REMOTE}" "${CURRENT_BRANCH}"

  ok "Pull --rebase concluído com sucesso."

else
  warn "Pull --rebase ignorado."
fi

#######################################
# Push
#######################################
if [[ "${DO_PUSH}" == "true" ]]; then

  echo

  if confirm "Deseja executar git push agora?"; then

    git push "${TARGET_REMOTE}" "${CURRENT_BRANCH}"

    ok "Push concluído com sucesso."

  else
    warn "Push ignorado."
  fi

else
  warn "Push desabilitado por parâmetro --no-push."
fi

#######################################
# Resumo final
#######################################
echo

ok "Processo finalizado."

log "Status final:"

git status --short || true

echo

log "Último commit:"

git --no-pager log -1 --stat

