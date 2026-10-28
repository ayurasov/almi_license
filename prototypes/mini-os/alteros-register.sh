#!/usr/bin/env bash
# mini-os: a prototype of the AlterOS registration (registration.sh) for manual tests of the
# licensing server and as a sample to carry into the OS (section 12.1 of document 2).
#
#   alteros-register.sh [--server URL] [--state DIR] [--cacert CA.pem] [--html] register
#   alteros-register.sh [--state DIR] status
#   alteros-register.sh [--state DIR] update      the repository updates (capability repo_updates)
#
# register: GET {server}/api/activate/?data=<MD5 of the machine>&host=<hostname>&lic=<key>&format=json
# The key comes from ALMI_LICENSE_KEY or is asked without echo: never an argument (shell history,
# process list) and never written to the log or the state, only its last four characters.
# Stage 1 runs AlterOS in monitor mode (expiry_action none): a refused registration does not stop
# the OS. ENFORCE=1 shows the behaviour of a later stage: no repository updates unregistered.
set -euo pipefail

server="${ALMI_LICENSE_SERVER_URL:-https://license.alter-os.ru}"
state="${ALMI_STATE_DIR:-/var/lib/alteros-registration}"
cacert=""
html=0
while [[ $# -gt 0 && "$1" == --* ]]; do
  case "$1" in
    --server) server="$2"; shift 2 ;;
    --state) state="$2"; shift 2 ;;
    --cacert) cacert="$2"; shift 2 ;;
    --html) html=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
command="${1:-status}"

# The machine: MD5 of /etc/machine-id (32 hex, as data of the LK); it stays the same across
# reinstalls of the registration and changes with the OS installation.
machine_data() {
  local source=/etc/machine-id
  [[ -r "$source" ]] || source=/var/lib/dbus/machine-id
  [[ -r "$source" ]] || { echo "no machine-id" >&2; exit 1; }
  md5sum < "$source" | cut -c1-32
}

json_field() {  # json_field FILE NAME: a field of the answer, or empty
  python3 -c 'import json,sys
try: print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))
except Exception: print("")' "$1" "$2"
}

register() {
  local key="${ALMI_LICENSE_KEY:-}"
  if [[ -z "$key" ]]; then read -rsp "Ключ лицензии: " key; echo; fi
  [[ -n "$key" ]] || { echo "Ключ не указан." >&2; exit 2; }
  mkdir -p "$state" && chmod 700 "$state"
  local answer status
  answer="$(mktemp)"
  trap 'rm -f "$answer"' RETURN
  local args=(-sS -G --max-time 30 -o "$answer" -w '%{http_code}' "$server/api/activate/"
    --data-urlencode "data=$(machine_data)" --data-urlencode "host=$(hostname)" --data-urlencode "lic=$key")
  [[ -n "$cacert" ]] && args+=(--cacert "$cacert")
  [[ "$html" == 0 ]] && args+=(--data-urlencode "format=json")
  if ! status="$(curl "${args[@]}")"; then
    echo "Нет связи с сервером лицензирования $server. Система работает, регистрацию можно повторить позже."
    return 1
  fi
  local message ok used total
  if [[ "$html" == 1 ]]; then
    # The page of the LK: the result is in <p class="result">.
    message="$(sed -n 's/.*<p class="result">\(.*\)<\/p>.*/\1/p' "$answer")"
    ok=$([[ "$status" == 200 ]] && echo True || echo False)
    used="" total=""
  else
    message="$(json_field "$answer" message)"
    ok="$(json_field "$answer" success)"
    used="$(json_field "$answer" used)" total="$(json_field "$answer" total)"
  fi
  echo "$message${total:+ (использовано $used из $total)}"
  if [[ "$ok" == "True" ]]; then
    umask 077
    printf 'registered_at=%s\nkey_tail=%s\nserver=%s\nused=%s\ntotal=%s\n' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${key: -4}" "$server" "$used" "$total" > "$state/registration"
    return 0
  fi
  if [[ "$status" == 429 ]]; then echo "Повторите через несколько минут."; fi
  return 1
}

show_status() {
  if [[ -s "$state/registration" ]]; then
    # shellcheck disable=SC1091
    source "$state/registration"
    # shellcheck disable=SC2154 # registered_at, server, key_tail come from the state file
    echo "Система зарегистрирована $registered_at на $server (ключ …$key_tail)."
  else
    echo "Система не зарегистрирована. Выполните: alteros-register.sh register"
    return 1
  fi
}

update() {
  if show_status > /dev/null; then
    echo "Обновления из репозитория разрешены (repo_updates)."
  elif [[ "${ENFORCE:-0}" == 1 ]]; then
    echo "Обновления из репозитория недоступны: система не зарегистрирована."
    return 1
  else
    echo "Система не зарегистрирована; обновления работают (этап 1: режим наблюдения)."
  fi
}

case "$command" in
  register) register ;;
  status) show_status ;;
  update) update ;;
  *) echo "commands: register | status | update" >&2; exit 2 ;;
esac
