---
name: images-to-pdf
description: Combine image files (PNG, JPG, JPEG, WEBP, BMP, TIFF, GIF) from a folder into a single PDF. Use when the user asks to "make a pdf of these screenshots", "combine images into a pdf", "create a pdf from these pictures", or similar requests to bundle images into one PDF document.
---

# images-to-pdf

Combine image files in a folder into a single PDF, one image per page, sorted by filename.

## How to run

Use Python with `img2pdf` (already installed on this machine — verified on Windows). It preserves image quality losslessly and handles alpha channels correctly.

```python
import img2pdf, glob, os
folder = r'<absolute path to folder>'
exts = ('*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp', '*.tif', '*.tiff', '*.gif')
files = []
for ext in exts:
    files.extend(glob.glob(os.path.join(folder, ext)))
    files.extend(glob.glob(os.path.join(folder, ext.upper())))
files = sorted(set(files))
out = os.path.join(folder, '<output-name>.pdf')
with open(out, 'wb') as f:
    f.write(img2pdf.convert(files))
print('Created:', out, '-', len(files), 'pages')
```

Run via the PowerShell tool with `python -c "..."`.

## Defaults and conventions

- **Source folder**: the current working directory unless the user specifies otherwise.
- **File order**: sort by filename. Screenshot filenames with timestamps (e.g. `Screenshot 2026-05-03 193555.png`) sort chronologically this way.
- **Output filename**: derive from the folder name (slugified — replace spaces with underscores), saved into the same folder. Example: folder `gladiator sssaaa` → `gladiator_sssaaa.pdf`. If the user names it, use their name.
- **Page size**: by default each page matches its source image's native dimensions. If the user asks for uniform pages ("same size", "consistent pages", "A4", etc.), use `layout_fun` (see below).
- **GIFs**: only the first frame is embedded (img2pdf default).

## Uniform page size

When the user wants every page to be the same size, pass a `layout_fun` to `img2pdf.convert`. img2pdf scales each image to fit the page while preserving its aspect ratio (so portraits and landscapes both work on the same page size).

```python
# A4 portrait (210 × 297 mm). Use (297, 210) for landscape.
layout = img2pdf.get_layout_fun(pagesize=(img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297)))
f.write(img2pdf.convert(files, layout_fun=layout))
```

Pick orientation based on the images: if most are taller than wide, use portrait; otherwise landscape. For US Letter use `img2pdf.in_to_pt(8.5), img2pdf.in_to_pt(11)`. If the user names a specific size, honor it.

## Reporting

After creating the PDF, report: output path, page count, and file size. Keep it to one line.

## Edge cases

- **No images found**: tell the user and stop — don't create an empty PDF.
- **Single image**: still works — produces a 1-page PDF.
- **Mixed orientations / sizes**: by default each page matches its source image's native dimensions. For uniform pages, use the `layout_fun` pattern above.
- **Alpha channel warnings**: img2pdf prints "Image contains an alpha channel..." to stderr — this is informational, not an error. Don't surface it to the user.
- **CMYK / unusual color spaces**: if img2pdf rejects an image, fall back to opening it with Pillow, converting to RGB, and saving to a temp PNG before passing to img2pdf.
