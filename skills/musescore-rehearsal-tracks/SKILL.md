---
name: musescore-rehearsal-tracks
description: Full choir rehearsal-track pipeline for a MuseScore 4 score (.mscz) — splits shared vocal staves (S/A, T/B), sets every track to Muse Keys → Grand Piano, and exports one MP3 per voice with that voice at max volume. Use when the user wants rehearsal/practice MP3s "from start to finish", asks to run split voices + piano sound + voice MP3 in sequence, or gives a choir score with shared staves and wants per-voice tracks.
---

# Rehearsal tracks: split → piano sound → voice MP3s

Runs three sibling skills in sequence, each through its own script:

1. `musescore-split-voices` splits every shared vocal staff.
2. `musescore-piano-sound` sets every track to Muse Keys / Grand Piano and adds mixer tracks for
   the new staves.
3. `musescore-voice-mp3` exports one MP3 per voice, with that voice at +12 dB.

All three skills must be installed next to this one (same `skills` folder). Read their SKILL.md
files if a step fails or needs explaining.

## Workflow

1. **Preview the plan** (Python 3, standard library only):

   ```
   python -B <skill-dir>/scripts/rehearsal_tracks.py "SCORE.mscz" --dry-run
   ```

   Shared staves are detected by name: a single-staff part whose name holds two voices
   (`S A`, `Soprano/Alto`, `T<br/>B`, `Tenor & Bass`). Its words become the new staff names, with
   the higher voice on the upper staff. If a shared staff is missed or its names are wrong, give
   the splits explicitly. Staff numbers count every staff in the score, and a piano counts as 2:

   ```
   --split 1:Sopran:Alt --split 3:Tenor:Bass
   ```

   Use `--no-split` if the voices already have their own staves.

2. **Run it** (drop `--dry-run`). Output goes to `<score folder>/<score> rehearsal/`, or to
   `--out-dir DIR` if given:
   - `<score>.mscz`, the processed score, so the user can open it and check the split
   - `<score> - <voice>.mp3`, one per voice

   Other options: `--master-db` (default −6, avoids clipping), `--others-db DB` (turns the other
   tracks down for a stronger featured voice), `--divisi upper|lower`, `--bitrate KBPS`.

   It takes about 10–15 s per voice. The original score is not modified. If a step fails, the
   pipeline stops and nothing more is written.

3. **Report to the user** from the printed output:
   - the split report: 3-note chords, removed ties, filled gaps, copied lyrics. These are the
     spots worth checking in the processed score.
   - tracks that were added or changed to piano
   - the MP3 files, and any tracks that stayed muted

4. **Optional check:** render the processed score and look at a page with the split staves:
   `"/c/Program Files/MuseScore 4/bin/MuseScore4.exe" -o check.png "<out>/<score>.mscz"`
   (write the PNGs to the scratchpad).
