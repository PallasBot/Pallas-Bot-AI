# shellcheck shell=bash
# CUDA 版本与 CUDA_HOME 探测（供 ctl / celery / Docker startup 共用）。
# 版本常量见同目录 cuda.env。

_CUDA_ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck disable=SC1091
source "${_CUDA_ENV_DIR}/cuda.env"

detect_cuda_home() {
  if [[ -n "${CUDA_HOME:-}" && -d "${CUDA_HOME}" ]]; then
    return 0
  fi

  local candidates=()
  local path=""

  if [[ -d /usr/local/cuda ]]; then
    candidates+=(/usr/local/cuda)
  fi

  # 匹配 /usr/local/cuda-12.*（含 12.4 / 12.8 / 未来 12.x），按版本号取最高
  shopt -s nullglob
  for path in /usr/local/cuda-12.*; do
    [[ -d "$path" ]] && candidates+=("$path")
  done
  shopt -u nullglob

  if [[ ${#candidates[@]} -eq 0 ]]; then
    return 1
  fi

  local sorted=()
  mapfile -t sorted < <(printf '%s\n' "${candidates[@]}" | sort -V -r)
  export CUDA_HOME="${sorted[0]}"
  return 0
}
