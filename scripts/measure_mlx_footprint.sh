#!/usr/bin/env bash
# POST_EG2 F4: phys_footprint around ~20 varied requests. Does not start or restart services.
# Prints idle / pre / peak / post-idle for mlx-speech, mlx-transcribe, or both (the default).
# The orchestrator runs this on a quiet host. REQUESTS, SETTLE_S, and HOST override the defaults.
set -uo pipefail

REQUESTS="${REQUESTS:-20}"
SETTLE_S="${SETTLE_S:-5}"
HOST="${HOST:-127.0.0.1}"
SAMPLE_S="${SAMPLE_S:-0.5}"
tmpdir=""

usage() {
  echo "usage: $0 [mlx-speech|mlx-transcribe]" >&2
  return 2
}

service_spec() {
  case "$1" in
    mlx-speech)
      PORT="${MLX_SPEECH_PORT:-8918}"
      LABEL="com.portal5.mlx-speech"
      ;;
    mlx-transcribe)
      PORT="${MLX_TRANSCRIBE_PORT:-8924}"
      LABEL="com.portal5.mlx-transcribe"
      ;;
    *)
      return 2
      ;;
  esac
}

launchd_pid() {
  launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null |
    awk '/^[[:space:]]*pid = / { print $3; exit }'
}

python_pid() {
  ps -A -o pid=,ppid=,comm= | python3 -c '
import sys
root = int(sys.argv[1])
comm, children = {}, {}
for line in sys.stdin:
    parts = line.split(None, 2)
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
        continue
    pid, ppid = int(parts[0]), int(parts[1])
    comm[pid] = parts[2]
    children.setdefault(ppid, []).append(pid)
queue, seen, found = [root], set(), None
while queue:
    current = queue.pop(0)
    if current in seen:
        continue
    seen.add(current)
    name = comm.get(current, "").split(" ", 1)[0].rsplit("/", 1)[-1].lower()
    if name.startswith("python"):
        found = current
        break
    queue.extend(children.get(current, []))
if found is None:
    raise SystemExit(1)
print(found)
' "$1"
}

footprint_bytes() {
  local text
  text="$(footprint -p "$1" 2>/dev/null || true)"
  python3 -c '
import re, sys
text = sys.stdin.read()
match = re.search(r"phys_footprint:\s*([0-9.]+)\s*([KMGT]?B)", text, re.I)
scale = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
if not match:
    raise SystemExit(1)
print(int(float(match.group(1)) * scale[match.group(2).upper()]))
' <<<"$text"
}

fmt_gib() {
  python3 -c 'import sys; print(f"{int(sys.argv[1]) / 1024**3:.3f} GiB")' "$1"
}

emit_sample() {
  local name="$1" bytes="$2"
  if [[ -z "$bytes" ]]; then
    echo "${name}=missing"
    return 1
  fi
  echo "${name}=${bytes} $(fmt_gib "$bytes")"
}

send_speech() {
  local payload
  payload="$(python3 -c 'import json,sys; n=int(sys.argv[1]); print(json.dumps({"model":"kokoro","input":"Hello. "*n,"voice":"af_heart"}))' "$1")"
  curl -sf -o /dev/null --max-time 180 \
    -H "Content-Type: application/json" \
    --data "$payload" \
    "http://${HOST}:${PORT}/v1/audio/speech"
}

write_wav() {
  python3 -c '
import sys, wave
path, seconds = sys.argv[1], float(sys.argv[2])
sr = 16000
count = max(1, int(seconds * sr))
period = max(1, sr // 220)
data = bytes(180 if (i % period) < period // 2 else 60 for i in range(count))
with wave.open(path, "wb") as handle:
    handle.setnchannels(1)
    handle.setsampwidth(1)
    handle.setframerate(sr)
    handle.writeframes(data)
' "$1" "$2"
}

send_transcribe() {
  local index="$1" dir="$2" seconds wav
  seconds="$(python3 -c 'import sys; i=int(sys.argv[1]); print(0.5 + 0.5 * (i - 1))' "$index")"
  wav="${dir}/clip-${index}.wav"
  write_wav "$wav" "$seconds"
  curl -sf -o /dev/null --max-time 180 \
    -F "file=@${wav};type=audio/wav" \
    -F "language=en" \
    "http://${HOST}:${PORT}/v1/audio/transcribe-with-speakers"
}

sample_loop() {
  local pid="$1" dir="$2" bytes
  while [[ -f "${dir}/sampling" ]]; do
    bytes="$(footprint_bytes "$pid" || true)"
    if [[ -n "$bytes" ]]; then
      echo "$bytes" >> "${dir}/samples"
    fi
    sleep "$SAMPLE_S"
  done
}

peak_of() {
  python3 -c '
import sys
vals = [int(line) for line in sys.stdin if line.strip().isdigit()]
if not vals:
    raise SystemExit(1)
print(max(vals))
' <"$1"
}

finish_dir() {
  [[ -n "${tmpdir}" ]] && rm -rf "${tmpdir}"
  tmpdir=""
}

measure_one() {
  local service="$1"
  local root="" py_pid="" idle="" pre="" peak="" post=""
  local failures=0 missing=0 sampler=0 i=""
  PORT=""
  LABEL=""
  if ! service_spec "$service"; then
    echo "ERROR: unknown service ${service}" >&2
    return 2
  fi
  tmpdir="$(mktemp -d)"
  echo "== ${service} port=${PORT} label=${LABEL} requests=${REQUESTS} =="
  echo "swap: $(sysctl -n vm.swapusage 2>/dev/null || echo unavailable)"
  root="$(launchd_pid || true)"
  if [[ -z "$root" ]]; then
    echo "ERROR: ${LABEL} has no launchd pid" >&2
    finish_dir
    return 2
  fi
  py_pid="$(python_pid "$root" || true)"
  if [[ -z "$py_pid" ]]; then
    echo "ERROR: no python descendant of pid ${root}" >&2
    finish_dir
    return 2
  fi
  echo "pid=${py_pid}"
  idle="$(footprint_bytes "$py_pid" || true)"
  if [[ -z "$idle" ]]; then
    echo "ERROR: footprint -p ${py_pid} produced no phys_footprint" >&2
    finish_dir
    return 2
  fi
  if ! curl -sf --max-time 5 "http://${HOST}:${PORT}/health" >/dev/null; then
    echo "ERROR: ${service} not answering on ${HOST}:${PORT}" >&2
    finish_dir
    return 2
  fi
  pre="$(footprint_bytes "$py_pid" || true)"
  if [[ -z "$pre" ]]; then
    echo "ERROR: footprint -p ${py_pid} produced no phys_footprint" >&2
    finish_dir
    return 2
  fi
  : >"${tmpdir}/samples"
  touch "${tmpdir}/sampling"
  sample_loop "$py_pid" "$tmpdir" &
  sampler=$!
  for i in $(seq 1 "$REQUESTS"); do
    if [[ "$service" == "mlx-speech" ]]; then
      send_speech "$i" || failures=$((failures + 1))
    else
      send_transcribe "$i" "$tmpdir" || failures=$((failures + 1))
    fi
  done
  rm -f "${tmpdir}/sampling"
  wait "$sampler" || true
  peak="$(peak_of "${tmpdir}/samples" || true)"
  sleep "$SETTLE_S"
  post="$(footprint_bytes "$py_pid" || true)"
  emit_sample idle_bytes "$idle" || missing=$((missing + 1))
  emit_sample pre_bytes "$pre" || missing=$((missing + 1))
  emit_sample peak_bytes "$peak" || missing=$((missing + 1))
  emit_sample post_idle_bytes "$post" || missing=$((missing + 1))
  echo "failed_requests=${failures}"
  finish_dir
  if [[ "$missing" -gt 0 ]]; then
    return 2
  fi
  if [[ "$failures" -gt 0 ]]; then
    return 1
  fi
  return 0
}

main() {
  local worst=0 rc=0 service
  local -a targets=()
  trap '[[ -n "${tmpdir}" ]] && rm -rf "${tmpdir}"' EXIT
  if [[ "$#" -eq 0 ]]; then
    targets=(mlx-speech mlx-transcribe)
  elif [[ "$#" -eq 1 ]]; then
    targets=("$1")
  else
    usage
    return 2
  fi
  for service in "${targets[@]}"; do
    measure_one "$service"
    rc=$?
    if [[ "$rc" -gt "$worst" ]]; then
      worst=$rc
    fi
  done
  return "$worst"
}

main "$@"
