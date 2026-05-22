#!/bin/bash
set -euo pipefail

DEFAULT_PROXY_URL="http://localhost:8081"
PROXY_URL="${PROXY_URL:-$DEFAULT_PROXY_URL}"

usage() {
    cat <<'USAGE'
Usage:
  ./test_proxy.sh [--url URL] status
  ./test_proxy.sh [--url URL] devices
  ./test_proxy.sh [--url URL] action <L1|L2|B1|B2> <on|off>
  ./test_proxy.sh [--url URL] control <L1|L2|B1|B2> <enable|disable>
  ./test_proxy.sh [--url URL] <on|off|enable|disable> <L1|L2|B1|B2>
  ./test_proxy.sh --help

Description:
  Test helper for Environment/Lab/proxy.py. It can:
  - read the current upstream state via /status
  - read administrative device enablement via /devices
  - turn devices on or off via /action
  - enable or disable devices via /control

Options:
  --url URL   Proxy base URL. Defaults to PROXY_URL if set, otherwise
              http://localhost:8081
  --help      Show this help message

Examples:
  ./test_proxy.sh status
  ./test_proxy.sh devices
  ./test_proxy.sh action L1 on
  ./test_proxy.sh control B2 disable
  ./test_proxy.sh on L2
  ./test_proxy.sh disable B1
USAGE
}

fail() {
    echo "Error: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "'$1' is required"
}

normalize_device() {
    local device="$1"
    case "$device" in
        L1|L2|B1|B2)
            printf '%s\n' "$device"
            ;;
        *)
            fail "invalid device '$device' (expected one of: L1, L2, B1, B2)"
            ;;
    esac
}

bool_from_action() {
    local action="$1"
    case "$action" in
        on|enable|true)
            printf 'true\n'
            ;;
        off|disable|false)
            printf 'false\n'
            ;;
        *)
            fail "invalid action '$action'"
            ;;
    esac
}

post_json() {
    local endpoint="$1"
    local body="$2"
    curl --silent --show-error \
        --header 'Content-Type: application/json' \
        --request POST \
        --data "$body" \
        "$PROXY_URL/$endpoint"
    printf '\n'
}

get_json() {
    local endpoint="$1"
    curl --silent --show-error "$PROXY_URL/$endpoint"
    printf '\n'
}

main() {
    require_command curl

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help|-h)
                usage
                exit 0
                ;;
            --url)
                [[ $# -ge 2 ]] || fail "--url requires a value"
                PROXY_URL="$2"
                shift 2
                ;;
            --url=*)
                PROXY_URL="${1#*=}"
                shift
                ;;
            *)
                break
                ;;
        esac
    done

    [[ $# -gt 0 ]] || {
        usage
        exit 1
    }

    case "$1" in
        status)
            [[ $# -eq 1 ]] || fail "status takes no additional arguments"
            get_json status
            ;;
        devices)
            [[ $# -eq 1 ]] || fail "devices takes no additional arguments"
            get_json devices
            ;;
        action)
            [[ $# -eq 3 ]] || fail "usage: ./test_proxy.sh action <device> <on|off>"
            local device
            local activate
            device="$(normalize_device "$2")"
            activate="$(bool_from_action "$3")"
            post_json action "{\"$device\": $activate}"
            ;;
        control)
            [[ $# -eq 3 ]] || fail "usage: ./test_proxy.sh control <device> <enable|disable>"
            local device
            local activate
            device="$(normalize_device "$2")"
            activate="$(bool_from_action "$3")"
            post_json control "{\"device\": \"$device\", \"activate\": $activate}"
            ;;
        on|off)
            [[ $# -eq 2 ]] || fail "usage: ./test_proxy.sh $1 <device>"
            local device
            local activate
            device="$(normalize_device "$2")"
            activate="$(bool_from_action "$1")"
            post_json action "{\"$device\": $activate}"
            ;;
        enable|disable)
            [[ $# -eq 2 ]] || fail "usage: ./test_proxy.sh $1 <device>"
            local device
            local activate
            device="$(normalize_device "$2")"
            activate="$(bool_from_action "$1")"
            post_json control "{\"device\": \"$device\", \"activate\": $activate}"
            ;;
        *)
            fail "unknown command '$1' (use --help)"
            ;;
    esac
}

main "$@"
