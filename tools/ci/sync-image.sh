#!/usr/bin/env bash
set -euo pipefail
: "${SOURCE_IMAGE:?Missing source image}"
: "${SOURCE_DIGEST:?Missing source digest}"
: "${DESTINATION_TAGS:?Missing destination tags}"

# Give the first large upload enough time to complete: interrupted blobs restart
# on each attempt. Existing destination blobs are reused by skopeo.
while IFS= read -r destination; do
  [[ -n "$destination" ]] || continue
  echo "::group::Copy to $destination"
  copied=false
  for attempt in 1 2; do
    echo "Attempt $attempt/2 (maximum 20 minutes)"
    if timeout --signal=TERM --kill-after=15s 20m skopeo copy \
      --preserve-digests --authfile "$HOME/.docker/config.json" \
      "docker://$SOURCE_IMAGE@$SOURCE_DIGEST" "docker://$destination"; then
      copied=true
      break
    fi
    if [[ "$attempt" -lt 2 ]]; then sleep 10; fi
  done
  echo '::endgroup::'
  if [[ "$copied" != true ]]; then
    echo "::error::Aliyun copy failed for $destination; rerun the failed sync job. GHCR build remains available at $SOURCE_IMAGE@$SOURCE_DIGEST"
    exit 1
  fi
done <<< "$DESTINATION_TAGS"
printf '### Aliyun sync complete\n\nSource: `%s@%s`\n' "$SOURCE_IMAGE" "$SOURCE_DIGEST" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
