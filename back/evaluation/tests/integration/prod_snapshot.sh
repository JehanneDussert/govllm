#!/bin/sh
# SPDX-FileCopyrightText: 2025-2026 Jehanne Dussert <https://www.linkedin.com/in/jehanne-dussert>
# SPDX-License-Identifier: EUPL-1.2
#
# Read-only snapshot of the REAL deployment, to prove a test run wrote nothing to it:
# for every table of the govllm schema, the row count and PostgreSQL's cumulative
# insert/update/delete/truncate-visible counters (pg_stat_user_tables), plus the Redis
# key count and a checksum of the eval:scores cache. Only SELECT / read commands.
#
#     sh back/evaluation/tests/integration/prod_snapshot.sh > before.txt
#     sh back/evaluation/tests/integration/run.sh
#     sh back/evaluation/tests/integration/prod_snapshot.sh > after.txt
#     diff before.txt after.txt   # no output = no write
set -eu
docker exec langfuse-db psql -U langfuse -d langfuse -At -F ' ' -c "
SELECT 'pg', s.relname, (xpath('/row/c/text()',
         query_to_xml(format('SELECT count(*) AS c FROM govllm.%I', s.relname), false, true, '')))[1]::text,
       s.n_tup_ins, s.n_tup_upd, s.n_tup_del
FROM pg_stat_user_tables s WHERE s.schemaname = 'govllm' ORDER BY s.relname;"
docker exec langfuse-db psql -U langfuse -d langfuse -At -c \
  "SELECT 'pg schemas', string_agg(nspname, ',' ORDER BY nspname) FROM pg_namespace WHERE nspname LIKE 'govllm%';"
echo "redis dbsize $(docker exec redis redis-cli DBSIZE)"
echo "redis eval:scores $(docker exec redis sh -c 'for k in $(redis-cli --scan --pattern "eval:scores:*" | sort); do echo "$k $(redis-cli GET "$k")"; done' | md5sum | cut -c1-32)"
