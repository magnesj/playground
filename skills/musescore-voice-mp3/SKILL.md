---
name: musescore-voice-mp3
description: Export choir rehearsal MP3s from a MuseScore 4 score (.mscz) — one file per soprano/alto/tenor/bass part, each with that voice's mixer volume at max and the full song playing. Use when the user asks for "rehearsal tracks", "practice files per voice", "export MP3 for each voice/stemme", "sopran/alt/tenor/bass mp3", or similar.
---

# Export one rehearsal MP3 per voice

For each voice part, a temporary copy of the score gets that part's mixer volume set to the
maximum (+12 dB, the top of MuseScore's volume slider). MuseScore then exports the whole song
from the copy to `<score> - <part>.mp3`. The original score is not modified.

## Workflow

1. **Find the score.** It must be a `.mscz` saved by MuseScore 4, because the mixer volumes are
   stored in `audiosettings.json` inside it. Check which parts are found:

   ```
   python <skill-dir>/scripts/export_voice_mp3.py "SCORE.mscz" --list
   ```

   Parts are matched by name: soprano, sopran, S, S1, alto, alt, A, tenor, T, bass, B, and so on.
   The script checks the staff long name, the track name and the short name, and uses the first
   one that names a voice. These fields are often stale or just a number. Repeated names are
   numbered (`Tenor 1`, `Tenor 2`) so their files don't overwrite each other. If detection is
   wrong, pass the names shown by `--list` with `--parts "Sopran 1,Alt,Tenor,Bass"`.

2. **Export** (Python 3, standard library only; takes roughly 10–15 s per voice):

   ```
   python <skill-dir>/scripts/export_voice_mp3.py "SCORE.mscz" --master-db -6
   ```

   Options:
   - `--master-db -6` lowers the master volume. Boosting one voice by +12 dB clips at loud
     passages; −6 dB removes that and keeps the balance between voices. Use it unless the user
     says otherwise.
   - `--others-db DB` sets every other track (other voices, piano, percussion) to this volume, for
     a stronger "my voice in front" mix, e.g. `-12`. By default other tracks are left unchanged.
   - `--out-dir DIR` sets the output folder. The default is next to the score; a subfolder such
     as `mp3` keeps the score folder tidy if the user wants that.
   - `--bitrate KBPS` sets the MP3 bitrate.
   - `--musescore PATH` sets the MuseScore executable, if it isn't at
     `C:\Program Files\MuseScore 4\bin\MuseScore4.exe`.

3. **Read the report.** It prints one line per file. It also flags:
   - tracks that are muted in the score. They stay muted, since the user usually muted them on
     purpose. Tell the user.
   - a part whose name contains several voices (e.g. `T B` on one staff). It is exported as a
     single file. Suggest the `musescore-split-voices` skill first.
   - a part with no mixer track, which is skipped. Opening and saving the score in MuseScore
     fixes that.

4. **Tell the user** where the files are and which options were used.

## Notes

- Solo is cleared on all tracks and the featured voice is unmuted, so every file contains the
  whole song.
- Sounds (Muse Sounds or MS Basic) are whatever the score uses. Combine with
  `musescore-piano-sound` first if the user wants the voices to play as piano.
- Repeats and D.S./D.C. are played as in MuseScore playback.
- Measured on a test score: the original mix clipped 0.002% of samples. One voice at +12 dB with
  nothing else changed clipped 0.22%. With `--master-db -6` it was 0.001%.
