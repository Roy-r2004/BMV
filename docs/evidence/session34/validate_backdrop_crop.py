"""JOB 2 validation — the shipped detector over every real screen on disk.

Expected: CROP on the three salon s33 screens (the pink-backdrop run),
keep on everything else — including the tone-on-tone retail floats (a crop
there would shave card padding; the ring-vs-inner guard refuses) and
hedgefund's clipped-cards screen (content touches the canvas edge, no ring
to crop). Watermark strips are removed first; the pipeline crops
pre-watermark.

Run: docker run --rm -v "$PWD:/repo" -w /repo/consultant-service \
  --entrypoint sh bmv-consultant-py -c \
  'python /repo/docs/evidence/session34/validate_backdrop_crop.py'
"""

import glob
import sys

sys.path.insert(0, ".")
from PIL import Image

from app.pipeline.images import _floating_backdrop_bbox

paths = sorted(glob.glob("scripts/out/bakeoff/*/*s33-full/images/*/*_0.png"))
paths += sorted(glob.glob("scripts/out/bakeoff/*/*s33-full/images/*/candidates/*.png"))
paths += sorted(glob.glob("scripts/out/bakeoff/*/*s34-2k/images/*/*_0.png"))
paths += sorted(glob.glob("scripts/out/bakeoff/*/*s34-2k/images/*/candidates/*.png"))
paths += sorted(glob.glob("uploads/images/68/*_0.png"))

crops = 0
for p in paths:
    im = Image.open(p)
    raw = im.crop((0, 0, im.width, round(im.height / 1.06)))
    bbox = _floating_backdrop_bbox(raw)
    label = "/".join(p.split("/")[-4:]) if "bakeoff" in p else p
    if bbox:
        crops += 1
        l, t, r, b = bbox
        print(f"CROP  {label}  {raw.width}x{raw.height} -> {r - l}x{b - t}")
    else:
        print(f"keep  {label}")
print(f"\n{crops} cropped, {len(paths) - crops} kept, of {len(paths)}")
