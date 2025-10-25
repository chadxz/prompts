Goal: produce a weekly GitHub activity brief for the authenticated user within
the `convergint` organization.

1. From this directory determine the date window:

   ```sh
   END_DATE=$(date -u +%F)
   START_DATE=$(python3 - <<'PY'
   from datetime import datetime, timedelta
   print((datetime.utcnow() - timedelta(days=6)).strftime("%Y-%m-%d"))
   PY
   )
   ```

2. Execute the collector and capture its JSON output:

   ```sh
   activity_json=$(./collect_activity.sh --start "$START_DATE" --end "$END_DATE")
   ```

3. Parse `activity_json`, which contains authored and reviewed pull requests
   (titles, bodies, URLs, repo names, timestamps). Use it to produce the final
   response with two parts:
   - A concise prose paragraph summarizing overall activity (themes, counts,
     open follow-up).
   - A bullet list with key specifics (authored PRs grouped by state, notable
     reviews, include links when helpful).

4. Avoid repeating identical information between the paragraph and bullets; keep
   the paragraph high level and the bullets detail-oriented.
