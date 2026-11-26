#!/bin/sh
set -eu

SANDBOX_LAB_EXEC=${SANDBOX_LAB_EXEC:-false}
LAB_TARGET_NETWORK=${LAB_TARGET_NETWORK:-}
LAB_EXEC_NETWORK=portal5-labexec
status_dir=${PORTAL5_LAB_STATUS_DIR:-/run/portal5}
status_file="$status_dir/lab-network-status"
mkdir -p "$status_dir"
rm -f "$status_file"

setup_lab_network() {
    [ -n "$LAB_TARGET_NETWORK" ] || return 1
    case "$LAB_TARGET_NETWORK" in
        */* ) ;;
        * ) return 1 ;;
    esac
    printf '%s\n' "$LAB_TARGET_NETWORK" | awk -F '[./]' '
        NF != 5 { exit 1 }
        {
            for (i = 1; i <= 4; i++) if ($i !~ /^[0-9]+$/ || $i > 255) exit 1
            if ($5 !~ /^[0-9]+$/ || $5 < 16 || $5 > 32) exit 1
            if (!($1 == 10 || ($1 == 172 && $2 >= 16 && $2 <= 31) || ($1 == 192 && $2 == 168)) ) exit 1
        }
    ' || return 1

    if ! docker network inspect portal5-labexec >/dev/null 2>&1; then
        docker network create --driver bridge \
            --opt com.docker.network.bridge.enable_icc=false \
            --label portal5.lab_exec=true \
            --label "portal5.lab_target_network=$LAB_TARGET_NETWORK" \
            portal5-labexec >/dev/null || return 1
    fi
    network_info=$(docker network inspect --format \
        '{{.Id}}|{{.Driver}}|{{.Internal}}|{{index .Labels "portal5.lab_exec"}}|{{index .Labels "portal5.lab_target_network"}}|{{index .Options "com.docker.network.bridge.enable_icc"}}' \
        portal5-labexec) || return 1
    network_id=$(printf '%s' "$network_info" | cut -d '|' -f1)
    driver=$(printf '%s' "$network_info" | cut -d '|' -f2)
    internal=$(printf '%s' "$network_info" | cut -d '|' -f3)
    lab_label=$(printf '%s' "$network_info" | cut -d '|' -f4)
    target_label=$(printf '%s' "$network_info" | cut -d '|' -f5)
    inter_container=$(printf '%s' "$network_info" | cut -d '|' -f6)
    [ "$driver" = bridge ] && [ "$internal" = false ] || return 1
    [ "$lab_label" = true ] && [ "$target_label" = "$LAB_TARGET_NETWORK" ] || return 1
    [ "$inter_container" = false ] || return 1
    bridge="br-$(printf '%s' "$network_id" | cut -c1-12)"

    iptables -w -N DOCKER-USER 2>/dev/null || true
    iptables -w -N PORTAL5-LABEXEC 2>/dev/null || true
    iptables -w -F PORTAL5-LABEXEC || return 1
    command -v ip >/dev/null 2>&1 || return 1
    outer_subnets=$(ip -4 route show dev eth0 | awk '$1 != "default" && $1 ~ /\// { print $1 }') || return 1
    for subnet in $outer_subnets; do
        iptables -w -A PORTAL5-LABEXEC -i "$bridge" -d "$subnet" -j DROP || return 1
    done
    outer_gateways=$(ip -4 route show default dev eth0 | awk '{ for (i = 1; i <= NF; i++) if ($i == "via") print $(i + 1) }') || return 1
    for gateway in $outer_gateways; do
        iptables -w -A PORTAL5-LABEXEC -i "$bridge" -d "$gateway/32" -j DROP || return 1
    done
    for network in $(docker network ls --format '{{.Name}}'); do
        [ "$network" = "$LAB_EXEC_NETWORK" ] && continue
        subnets=$(docker network inspect --format '{{range .IPAM.Config}}{{.Subnet}} {{end}}' "$network") || return 1
        for subnet in $subnets; do
            case "$subnet" in *:*) continue ;; esac
            iptables -w -A PORTAL5-LABEXEC -i "$bridge" -d "$subnet" -j DROP || return 1
        done
    done
    iptables -w -A PORTAL5-LABEXEC -i "$bridge" -d "$LAB_TARGET_NETWORK" -j ACCEPT || return 1
    iptables -w -A PORTAL5-LABEXEC -i "$bridge" -j DROP || return 1
    iptables -w -A PORTAL5-LABEXEC -o "$bridge" \
        -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT || return 1
    iptables -w -A PORTAL5-LABEXEC -o "$bridge" -j DROP || return 1
    while iptables -w -C INPUT -i "$bridge" -j DROP 2>/dev/null; do
        iptables -w -D INPUT -i "$bridge" -j DROP || return 1
    done
    iptables -w -I INPUT 1 -i "$bridge" -j DROP || return 1
    while iptables -w -C DOCKER-USER -j PORTAL5-LABEXEC 2>/dev/null; do
        iptables -w -D DOCKER-USER -j PORTAL5-LABEXEC || return 1
    done
    iptables -w -I DOCKER-USER 1 -j PORTAL5-LABEXEC || return 1
    while iptables -w -C FORWARD -j DOCKER-USER 2>/dev/null; do
        iptables -w -D FORWARD -j DOCKER-USER || return 1
    done
    iptables -w -I FORWARD 1 -j DOCKER-USER || return 1

    command -v ip6tables >/dev/null 2>&1 || return 1
    ip6tables -w -N DOCKER-USER 2>/dev/null || true
    ip6tables -w -N PORTAL5-LABEXEC 2>/dev/null || true
    ip6tables -w -F PORTAL5-LABEXEC || return 1
    ip6tables -w -A PORTAL5-LABEXEC -i "$bridge" -j DROP || return 1
    ip6tables -w -A PORTAL5-LABEXEC -o "$bridge" \
        -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT || return 1
    ip6tables -w -A PORTAL5-LABEXEC -o "$bridge" -j DROP || return 1
    while ip6tables -w -C INPUT -i "$bridge" -j DROP 2>/dev/null; do
        ip6tables -w -D INPUT -i "$bridge" -j DROP || return 1
    done
    ip6tables -w -I INPUT 1 -i "$bridge" -j DROP || return 1
    while ip6tables -w -C DOCKER-USER -j PORTAL5-LABEXEC 2>/dev/null; do
        ip6tables -w -D DOCKER-USER -j PORTAL5-LABEXEC || return 1
    done
    ip6tables -w -I DOCKER-USER 1 -j PORTAL5-LABEXEC || return 1
    while ip6tables -w -C FORWARD -j DOCKER-USER 2>/dev/null; do
        ip6tables -w -D FORWARD -j DOCKER-USER || return 1
    done
    ip6tables -w -I FORWARD 1 -j DOCKER-USER || return 1

    iptables -w -C PORTAL5-LABEXEC -i "$bridge" -d "$LAB_TARGET_NETWORK" -j ACCEPT || return 1
    iptables -w -C PORTAL5-LABEXEC -i "$bridge" -j DROP || return 1
    iptables -w -C PORTAL5-LABEXEC -o "$bridge" \
        -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT || return 1
    iptables -w -C PORTAL5-LABEXEC -o "$bridge" -j DROP || return 1
    iptables -w -C INPUT -i "$bridge" -j DROP || return 1
    ip6tables -w -C PORTAL5-LABEXEC -i "$bridge" -j DROP || return 1
    ip6tables -w -C PORTAL5-LABEXEC -o "$bridge" -j DROP || return 1
    ip6tables -w -C INPUT -i "$bridge" -j DROP || return 1
    ip6tables -w -C DOCKER-USER -j PORTAL5-LABEXEC || return 1
    ip6tables -w -C FORWARD -j DOCKER-USER || return 1
    printf 'portal5-labexec-v1\n%s\n%s\n%s\n' \
        "$LAB_TARGET_NETWORK" "$network_id" "$bridge" >"$status_file"
}

initialize_lab_network() {
    attempt=0
    until docker info >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 60 ]; then
            printf 'daemon-unavailable\n' >"$status_file"
            echo "ERROR: DinD did not become ready" >&2
            return 1
        fi
        sleep 1
    done

    if [ "${SANDBOX_LAB_EXEC:-false}" = true ]; then
        if setup_lab_network; then
            echo "Lab exec firewall ready: $LAB_TARGET_NETWORK via $LAB_EXEC_NETWORK"
        else
            printf 'unavailable\n' >"$status_file"
            echo "ERROR: lab exec firewall setup failed; lab executor will be disabled" >&2
        fi
    else
        printf 'disabled\n' >"$status_file"
    fi
}

initialize_lab_network &
exec dockerd-entrypoint.sh "$@"
