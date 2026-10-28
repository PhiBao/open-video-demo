#!/usr/bin/env bash
# Scaffold a new video project: videos/<name>/{script,config}.
set -euo pipefail
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="${1:-}"

if [ -z "$name" ]; then
  echo "usage: ./scripts/new.sh <name>   (slug, e.g. acme-demo)" >&2
  exit 2
fi
if [[ ! "$name" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "name must be a slug: letters, digits, _ or -" >&2
  exit 2
fi

dest="$TEMPLATE/videos/$name"
if [ -e "$dest" ]; then
  echo "already exists: $dest" >&2
  exit 2
fi

mkdir -p "$dest/script" "$dest/config"
sed -e "s/\"name\": \"demo\"/\"name\": \"$name\"/" \
    -e "s#\"output\": \"out/demo.mp4\"#\"output\": \"out/$name.mp4\"#" \
    "$TEMPLATE/defaults/video.json" > "$dest/config/video.json"

cat > "$dest/script/story.json" <<EOF
{
  "_howto": "Product demo first: show the product's real surface, with real proof. Scenes by product type - web app: page scenes (s2 below); CLI/dev tool: term scenes with real copied output; API/agent: term for request -> result. See AGENTS.md. Rewrite every 'text' as narration, then delete this key.",
  "voice": "en-US-GuyNeural",
  "segments": [
    {
      "id": "s1_hook",
      "text": "TODO: one-sentence hook for $name. Speak numbers as words.",
      "scene": { "kind": "card", "template": "title" }
    },
    {
      "id": "s2_product",
      "text": "TODO: narrate what the viewer sees happening in the product.",
      "scene": {
        "_note": "placeholder app - replace src with your app URL or a local page; for a CLI/dev-tool product replace this whole scene with a 'term' scene (see AGENTS.md)",
        "kind": "page",
        "src": "videos/example/app/index.html",
        "zoom": 1.5,
        "wait_for": ["text=Ship with confidence"],
        "settle": 1.0,
        "actions": [
          { "action": "scrollTo", "sel": ".stats", "dur": 1.2, "after": 0.6 },
          { "action": "scrollTo", "sel": ".cta", "dur": 1.2, "after": 0.8 }
        ]
      }
    },
    {
      "id": "s3_close",
      "text": "TODO: one-line thesis, then where to find the project. Links on screen.",
      "scene": { "kind": "card", "template": "close" }
    }
  ]
}
EOF

echo "created videos/$name"
echo
echo "  1. write  videos/$name/script/story.json   (narration + scenes)"
echo "  2. edit   videos/$name/config/video.json   (branding, theme, voice)"
echo "  3. pick an intro that fits the product, not the default:"
echo "       title       centered (confident brand)"
echo "       title-left  editorial rail + kicker (investigative / devtool)"
echo "       title-soft  light calm card (human / clinical)"
echo "     set it as the first segment's scene template, then tune the"
echo "     \"theme\" colors in config/video.json to match the product."
echo "  4. run    ./scripts/run.sh --project $name"
echo
echo "This is a product demo: keep the product's real surface on screen."
echo "  web app / SaaS  -> page scenes (the scaffold's s2_product)"
echo "  CLI / dev tool  -> term scenes with real output (see AGENTS.md)"
