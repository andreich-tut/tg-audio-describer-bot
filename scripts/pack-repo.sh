#!/bin/bash
# Pack repository into a single AI-friendly file

npx repomix \
  --style plain \
  --remove-comments \
  --remove-empty-lines \
  --compress \
  --ignore 'README.md,QWEN.md,CLAUDE.md,docs/**/*.*,prompts/**/*.*,skills/**/*.*,tools/README.md' \
  -o docs/repomix-output.txt
