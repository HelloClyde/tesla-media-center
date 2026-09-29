#!/usr/bin/env bash
set -euo pipefail
: "${SOURCE_IMAGE:?Missing source image}"
: "${SOURCE_DIGEST:?Missing source digest}"
: "${DESTINATION_TAGS:?Missing destination tags}"

# One outer deadline covers all tags and retries. Existing destination blobs
# are reused by skopeo; --all preserves the AMD64 and ARM64 manifest list.
while IFS= read -r destination; do
  [[ -n "$destination" ]] || continue
  echo "::group::Copy to $destination"
  copied=false
  for attempt in 1 2 3; do
    echo "Attempt $attempt/3 (maximum 8 minutes)"
    if timeout --signal=TERM --kill-after=15s 8m skopeo copy \
      --all --preserve-digests --authfile "$HOME/.docker/config.json" \
      "docker://$SOURCE_IMAGE@$SOURCE_DIGEST" "docker://$destination"; then
      copied=true
      break
    fi
    if [[ "$attempt" -lt 3 ]]; then sleep "$((attempt * 10))"; fi
  done
  echo '::endgroup::'
  if [[ "$copied" != true ]]; then
    echo "::error::Aliyun copy failed for $destination; rerun the failed sync job. GHCR build remains available at $SOURCE_IMAGE@$SOURCE_DIGEST"
    exit 1
  fi
done <<< "$DESTINATION_TAGS"
printf '### Aliyun sync complete\n\nSource: `%s@%s`\n' "$SOURCE_IMAGE" "$SOURCE_DIGEST" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
