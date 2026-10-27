#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
# Remove the isolated stack (containers, network, generated config). Results in OUT are kept.
export MSYS_NO_PATHCONV=1
docker rm -f iso-ollama iso-litellm iso-pg iso-redis iso-langfuse iso-eval iso-runner-benchmark iso-runner-fewshot >/dev/null 2>&1
docker network rm govllm-iso >/dev/null 2>&1
rm -rf "$(cd "$(dirname "$0")" && pwd)/.state"
echo "isolated stack removed"
