#!/bin/bash -e

TEMP_FILES=()

cleanup() {
  for file in "${TEMP_FILES[@]}"; do
    if [[ -f "$file" ]]; then
      rm "$file"
    fi
  done
}

trap cleanup EXIT

function check_translation_file() {
  if [ $# -ne 1 ]; then
    echo "Usage: $0 <translation_file.ts>"
    exit 1
  fi
  local ts_file=$1

  echo "Checking '$ts_file' is up to date..."
  cp "$ts_file" "${ts_file/.ts/.a.ts}"
  TEMP_FILES+=("${ts_file/.ts/.a.ts}")
  cp "$ts_file" "${ts_file/.ts/.b.ts}"
  TEMP_FILES+=("${ts_file/.ts/.b.ts}")
  #
  pylupdate5 $LABELME_DIR/*.py $LABELME_DIR/widgets/*.py -ts "${ts_file/.ts/.b.ts}"
  diff <(sed -r 's/line="[0-9]+"//g' "${ts_file/.ts/.a.ts}") <(sed -r 's/line="[0-9]+"//g' "${ts_file/.ts/.b.ts}")

  echo "Checking '${ts_file} -> .qm' is up to date..."
  lrelease "$ts_file" -qm "${ts_file/.ts/.b.qm}" > /dev/null
  TEMP_FILES+=("${ts_file/.ts/.b.qm}")
  diff "${ts_file/.ts/.qm}" "${ts_file/.ts/.b.qm}"

  echo "Finished checking '$ts_file'."
}

HERE=$(dirname "$0")

LABELME_DIR="$HERE/../labelme"
TRANSLATE_DIR="$LABELME_DIR/translate"

check_translation_file "$TRANSLATE_DIR/zh_CN.ts"
