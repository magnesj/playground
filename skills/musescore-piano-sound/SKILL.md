---
name: musescore-piano-sound
description: Set the playback sound of all staves/instruments in a MuseScore 4 score (.mscz) to MuseSounds "Muse Keys → Grand Piano" without changing the notation. Use when the user asks to "make every staff play piano", "use Grand Piano sound for all parts", "assign Muse Keys Grand Piano to all staves", or wants a choir/rehearsal score to play back with piano.
---

# Give every staff the Muse Keys → Grand Piano sound

Does what picking **MuseSounds → Muse Keys → Grand Piano** in the Mixer does for each track, but for
all of them at once. Instrument names, clefs, and staff types stay as they are: a "Soprano" staff
is still a voice staff but plays back as piano. A new file is written; the original is not touched.

## How MuseScore stores it

The sound choice lives in `audiosettings.json` inside the `.mscz`, not in the `.mscx`. Each track
is keyed by `partId` + `instrumentId` (`voice`, `piano`, `chord_symbols`, …). The Grand Piano entry is:

```json
"resourceMeta": {
  "attributes": { "museCategory": "Muse Keys", "museName": "Grand Piano", "musePack": "Muse Keys",
                  "museUID": "167", "museVendorName": "Muse", "playbackSetupData": "keyboards.piano" },
  "hasNativeEditorSupport": false, "id": "167",
  "type": "muse_sampler_sound_pack", "vendor": "MuseSounds" }
```

Files saved by MuseScore versions before 4.6 use `"id": "Muse Keys\\Grand Piano\\167"`. The script
chooses the format from `<programVersion>`.

## Workflow

1. **Find the file.** List the folder. The input must be a `.mscz`, because a bare `.mscx` has no
   audio settings.

2. **Run the script** (Python 3, standard library only):

   ```
   python <skill-dir>/scripts/set_piano_sound.py "IN.mscz" "OUT.mscz"
   ```

   Unless the user asks to overwrite, name the output like the user's own versioning
   (e.g. `Song 02.mscz` → `Song 03.mscz`). Otherwise write it next to the input with a suffix.

3. **Read the report.** It prints one line per track with the old sound and the new one. Lines
   that say `added track` are parts that had no playback track yet (typically staves added by
   another script, e.g. `musescore-split-voices`). Without the added track, MuseScore would give
   those parts their default sound.

4. **Verify** that MuseScore loads the file and keeps the sounds after saving it again
   (default Windows path; work in the scratchpad):

   ```
   "/c/Program Files/MuseScore 4/bin/MuseScore4.exe" -o roundtrip.mscz "OUT.mscz"
   ```

   Then list `partId instrumentId museName` from `roundtrip.mscz`'s `audiosettings.json`. Every
   track except `metronome` should say `Grand Piano`.

5. **Tell the user** which tracks changed from another sound (e.g. `Muse Choir / Altos`) and which
   tracks were added.

## Notes

- The metronome track is left alone. Mixer volume, pan, reverb sends and solo/mute are kept. New
  tracks copy the `out` settings (aux sends, volume) of the first existing track.
- A `chord_symbols` track is added for a part whose staves contain `<Harmony>`, the same way
  MuseScore does it.
- Excerpt `audiosettings.json` files (generated parts) only store solo/mute, so they need no
  change.
- Mid-score instrument changes (`InstrumentChange`) that have no track yet are not added. They get
  their default sound until they are set in the Mixer.
