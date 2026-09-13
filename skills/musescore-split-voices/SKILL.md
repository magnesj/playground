---
name: musescore-split-voices
description: Split a shared two-part vocal staff in a MuseScore 4 score (.mscz/.mscx) — e.g. "Soprano/Alto" or "Tenor/Bass" written as chords and/or two voices on one staff — into two separate staves, duplicating unison passages on both. Use when the user asks to separate S/A or T/B (or any two-voice) staves, "give soprano and alto their own staff", "split the choir staff", or similar.
---

# Split a shared vocal staff in MuseScore

Turns one staff that carries two vocal parts (e.g. `S/A`) into two staves (`S`, `A`),
writing a new file and never touching the original.

## Workflow

1. **Find the file and the staff.** List the folder. Unzip the `.mscz` to the scratchpad and
   look at `<Part>` / `<trackName>` / `<longName>` to find the 1-based *staff number* to split
   (count every `<Staff>` inside every `<Part>` in order; a piano part counts as 2).
   Check `<programVersion>`: the script targets MuseScore 4.x files.

2. **Run the script** (Python 3, standard library only):

   ```
   python <skill-dir>/scripts/split_staff.py "IN.mscz" "OUT.mscz" --staff 1 --upper-name S --lower-name A
   ```

   Options:
   - `--staff N` — staff to split (default 1)
   - `--upper-name` / `--lower-name` — new staff names (default `S` / `A`; match the naming
     style already in the score, e.g. `T`/`B` or `Sopran`/`Alt`)
   - `--divisi upper|lower` — who gets the extra note(s) of 3+-note chords (default `upper`:
     upper staff gets the top two notes of a triad, lower gets the bottom one)

   The input can be `.mscz` or `.mscx`. For `.mscz` the embedded `.mscx` is renamed to match
   the output file name and `META-INF/container.xml` is updated.

3. **Read the report** the script prints. It lists every judgement call it made:
   lyrics copied between voices, unison notes shortened where voice 2 enters,
   dangling ties removed, gaps filled with rests. Mention these to the user.

4. **Verify by rendering** with MuseScore (default Windows path shown):

   ```
   "/c/Program Files/MuseScore 4/bin/MuseScore4.exe" -o check.png "OUT.mscz"
   ```

   This writes `check-1.png`, `check-2.png`, … — read the pages that contain the measures from
   the report and confirm the two staves look right (and that the file loads at all).
   Put the PNGs in the scratchpad, not next to the score.

5. **Tell the user** what was done, and list the ambiguous spots (3-note chords and how they were
   assigned, removed ties, filled gaps) so they can check them.

## How the notes are distributed

| Source on the shared staff | Upper staff | Lower staff |
|---|---|---|
| Single note, one voice (unison) | the note | the note (duplicated) |
| 2-note chord | top note | bottom note |
| 3+-note chord | top two (`--divisi upper`) | the rest |
| Bar with voice 1 + voice 2 | voice 1 (top notes of chords) | voice 2 where it has visible notes/rests, voice 1 bottom notes elsewhere |
| Lyrics only on one voice | copied onto a note starting at the same tick that has no lyrics | same |
| Voice-2 rest at a tick where voice 1 has a longer note (voice 2 enters later) | — | voice 1's note, shortened to the rest's value |

Also handled:
- Ties are re-targeted per staff (location `notes`/`voices` offsets rewritten); a tie whose
  target note no longer exists on that staff is removed and reported.
- System-level items (volta, segno/coda `Marker`, `Jump`, `Tempo`, `RehearsalMark`,
  `SystemText`, layout breaks, frames) stay only on the upper staff so they are not doubled.
- Dynamics, hairpins, staff text, clefs, key/time signatures are duplicated.
- The lower staff becomes a new `<Part>` directly after the original one (copied instrument,
  free MIDI channel); every bracket that spanned the old staff grows by one.
- `eid`s are removed from the new staff (MuseScore regenerates them; duplicates are not allowed).
- `<location>` jumps inside voices are understood; gaps in the lower staff become plain rests.

## Limitations (the script stops with an error instead of guessing)

- Tuplets on the staff being split.
- More than two voices in a bar.
- A lower-staff overlap that cannot be resolved.
- The staff belongs to a multi-staff part (e.g. a piano).

If the file has excerpts (generated parts), the script warns that they are not updated —
regenerate the parts in MuseScore afterwards.

If a limitation is hit, inspect the offending measures and either extend the script or edit
the XML for those measures by hand, then re-verify by rendering.
