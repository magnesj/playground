#!/usr/bin/env python3
"""Split a two-part vocal staff (e.g. "S/A" or "T/B") in a MuseScore 4 file
into two separate staves.

Rules
  * single notes (unison)        -> duplicated on both staves
  * 2-note chords                -> top note to upper staff, bottom note to lower
  * 3+-note chords               -> see --divisi (default: upper staff gets the top two)
  * voice 1 + voice 2 in a bar   -> upper staff = voice 1 (top notes of chords),
                                    lower staff = voice 2 where it has visible content,
                                    voice 1 bottom notes elsewhere
  * lyrics that exist only on one voice are copied to the other staff when a
    note starts at the same tick and has no lyrics of its own
  * ties are re-targeted; ties whose destination no longer exists are removed
  * system elements (volta, marker, jump, tempo, rehearsal marks, layout breaks,
    frames) are kept only on the upper staff

Usage
  python split_staff.py IN.mscz OUT.mscz [--staff N] [--upper-name S]
                        [--lower-name A] [--divisi upper|lower]
"""
import argparse
import copy
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from fractions import Fraction as Fr

DT = {'long': Fr(4), 'breve': Fr(2), 'whole': Fr(1), 'half': Fr(1, 2),
      'quarter': Fr(1, 4), 'eighth': Fr(1, 8), '16th': Fr(1, 16),
      '32nd': Fr(1, 32), '64th': Fr(1, 64), '128th': Fr(1, 128)}
SYSTEM_MEASURE_TAGS = {'Marker', 'Jump', 'LayoutBreak'}
SYSTEM_VOICE_TAGS = {'Tempo', 'RehearsalMark', 'SystemText'}

report = []


def fail(msg):
    sys.exit('ERROR: ' + msg)


def dur(el):
    if el.tag not in ('Chord', 'Rest'):
        return None
    t = el.findtext('durationType')
    if t == 'measure':
        return Fr(el.findtext('duration'))
    dots = int(el.findtext('dots') or 0)
    return DT[t] * (2 - Fr(1, 2 ** dots))


TUPLET_MEMBERS = set()  # id() of source Chord/Rest elements inside a tuplet


def timed(voice, where):
    out, t, ratio = [], Fr(0), None
    for el in voice:
        if el.tag == 'Tuplet':
            if ratio is not None:
                fail(f'{where}: nested tuplets are not supported by this script')
            ratio = Fr(int(el.findtext('normalNotes')), int(el.findtext('actualNotes')))
        elif el.tag == 'endTuplet':
            ratio = None
        d = dur(el)
        if d is not None and ratio is not None:
            d *= ratio
            TUPLET_MEMBERS.add(id(el))
        out.append((t, el, d))
        if d is not None:
            t += d
        elif el.tag == 'location':
            t += Fr(el.findtext('fractions') or '0')
    return out


def rests(length):
    """Plain rests filling `length` (largest values first)."""
    out = []
    for name, d in sorted(DT.items(), key=lambda x: -x[1]):
        while length >= d and d <= 1:
            r = ET.Element('Rest')
            ET.SubElement(r, 'durationType').text = name
            out.append(r)
            length -= d
    return out


def strip_eids(el):
    for p in el.iter():
        for c in list(p):
            if c.tag == 'eid':
                p.remove(c)


def reduce_chord(ch, part, divisi):
    notes = ch.findall('Note')
    if len(notes) < 2:
        return
    s = sorted(notes, key=lambda n: int(n.findtext('pitch')))
    if len(notes) == 2:
        keep = s[-1:] if part == 'U' else s[:1]
    else:
        n_upper = len(s) - 1 if divisi == 'upper' else 1
        keep = s[-n_upper:] if part == 'U' else s[:len(s) - n_upper]
    for n in notes:
        if n not in keep:
            ch.remove(n)


def copy_lyrics(src, dst):
    idx = list(dst).index(dst.find('Note'))
    for ly in reversed(src.findall('Lyrics')):
        dst.insert(idx, copy.deepcopy(ly))


def is_system(el):
    return el.tag in SYSTEM_VOICE_TAGS or (el.tag == 'Spanner' and el.get('type') == 'Volta')


def build(src, part, divisi):
    staff = ET.Element('Staff')
    mno = 0
    for child in src:
        if child.tag != 'Measure':
            if part == 'U':
                staff.append(copy.deepcopy(child))
            continue
        mno += 1
        where = f'measure {mno}'
        nm = ET.Element('Measure', child.attrib)
        for c in child:
            if c.tag != 'voice' and not (part == 'L' and c.tag in SYSTEM_MEASURE_TAGS):
                nm.append(copy.deepcopy(c))
        voices = child.findall('voice')
        if len(voices) > 2:
            fail(f'{where}: more than two voices')
        v0 = timed(voices[0], where)
        v1 = timed(voices[1], where) if len(voices) > 1 else []
        covered = [(t, t + d) for t, el, d in v1 if d is not None and el.findtext('visible') != '0']

        if part == 'U' or not covered:
            items = []
            for t, el, d in v0:
                if part == 'L' and is_system(el):
                    continue
                e = copy.deepcopy(el)
                if e.tag == 'Chord':
                    reduce_chord(e, part, divisi)
                items.append((t, el, d, e))
            if part == 'U' and v1:
                starts = {t: e for t, _, d, e in items if d is not None}
                for t, el, d in v1:
                    tgt = starts.get(t)
                    if el.tag == 'Chord' and el.findall('Lyrics') and tgt is not None \
                            and tgt.tag == 'Chord' and not tgt.findall('Lyrics'):
                        copy_lyrics(el, tgt)
                        report.append(f'upper m{mno}: lyrics copied from voice 2 at {t}')
            v = ET.SubElement(nm, 'voice')
            for *_, e in items:
                v.append(e)
            staff.append(nm)
            continue

        # lower staff in a bar with a real second voice
        def is_cov(t, d):
            return any(a < t + d and t < b for a, b in covered)

        end = max([t + d for t, _, d in v0 + v1 if d is not None])
        entries, pending = [], []
        for t, el, d in v0:
            if el.tag == 'location':
                continue
            if d is None:
                pending.append(el)
                continue
            keep = not is_cov(t, d)
            if keep and id(el) in TUPLET_MEMBERS:
                fail(f'{where}: voice-1 tuplet only partly replaced by voice 2; not supported')
            for p in pending:
                if (p.tag == 'Beam' and not keep) or is_system(p) or p.tag in ('Tuplet', 'endTuplet'):
                    continue
                entries.append((t, 0, copy.deepcopy(p), None))
            pending = []
            if keep:
                e = copy.deepcopy(el)
                if e.tag == 'Chord':
                    reduce_chord(e, 'L', divisi)
                entries.append((t, 1, e, d))
        entries += [(Fr(10 ** 6), 0, copy.deepcopy(p), None) for p in pending
                    if not is_system(p) and p.tag not in ('Tuplet', 'endTuplet')]

        v0_chords = {t: el for t, el, d in v0 if el.tag == 'Chord'}
        pending = []
        for t, el, d in v1:
            if el.tag == 'location':
                continue
            if d is None:
                pending.append(el)
                continue
            if el.findtext('visible') == '0':
                pending = []
                continue
            entries += [(t, 0, copy.deepcopy(p), None) for p in pending if not is_system(p)]
            pending = []
            e = copy.deepcopy(el)
            src_chord = v0_chords.get(t)
            if e.tag == 'Rest' and src_chord is not None and dur(src_chord) >= d:
                # unison note sung before voice 2 enters: keep it, shortened to the rest
                c = copy.deepcopy(src_chord)
                reduce_chord(c, 'L', divisi)
                c.find('durationType').text = e.findtext('durationType')
                for x in c.findall('dots'):
                    c.remove(x)
                if e.findtext('dots'):
                    x = ET.Element('dots')
                    x.text = e.findtext('dots')
                    c.insert(list(c).index(c.find('durationType')), x)
                for n in c.findall('Note'):
                    for sp in n.findall('Spanner'):
                        n.remove(sp)
                for ly in c.findall('Lyrics'):
                    for x in ly.findall('ticks_f') + ly.findall('ticks'):
                        ly.remove(x)
                report.append(f'lower m{mno}: kept unison note at {t} (shortened) before voice 2 enters')
                e = c
            elif e.tag == 'Chord' and not e.findall('Lyrics') and src_chord is not None \
                    and src_chord.findall('Lyrics'):
                copy_lyrics(src_chord, e)
                report.append(f'lower m{mno}: lyrics copied from voice 1 at {t}')
            entries.append((t, 2, e, d))
        entries += [(Fr(10 ** 6), 3, copy.deepcopy(p), None) for p in pending if not is_system(p)]
        entries.sort(key=lambda x: (x[0], x[1]))
        v = ET.SubElement(nm, 'voice')
        tt = Fr(0)
        for t, _, e, d in entries:
            if d is not None and t < tt:
                fail(f'{where}: voices overlap for the lower staff at {t}')
            if tt < t <= end:
                v.extend(rests(t - tt))
                report.append(f'lower m{mno}: filled gap {tt}-{t} with rest(s) - check rhythm')
                tt = t
            if d is not None:
                tt = t + d
            v.append(e)
        if tt < end:
            # insert before trailing non-duration elements
            tail = [x for x in list(v)[::-1]]
            idx = len(v)
            for x in tail:
                if dur(x) is not None:
                    break
                idx -= 1
            for k, r in enumerate(rests(end - tt)):
                v.insert(idx + k, r)
            report.append(f'lower m{mno}: filled gap {tt}-{end} with rest(s) - check rhythm')
        staff.append(nm)
    normalize_lyrics(staff, part)
    if part == 'L':
        strip_eids(staff)  # MuseScore regenerates missing eids; duplicates are not allowed
    return staff


def normalize_lyrics(staff, part):
    """One voice per staff now: lyrics placed above (to tell voices apart) go back below.
    If a chord has several lyrics for the same verse, the upper staff keeps the one that
    was placed above the shared staff and the lower staff keeps one that was below."""
    label = 'upper' if part == 'U' else 'lower'
    moved = 0
    for mi, m in enumerate(staff.findall('Measure')):
        for ch in m.iter('Chord'):
            by_verse = {}
            for ly in ch.findall('Lyrics'):
                by_verse.setdefault(ly.findtext('no') or '0', []).append(ly)
            for lys in by_verse.values():
                if len(lys) > 1:
                    above = [ly for ly in lys if ly.findtext('placement') == 'above']
                    below = [ly for ly in lys if ly.findtext('placement') != 'above']
                    pref = (above if part == 'U' else below) or lys
                    for ly in lys:
                        if ly is not pref[0]:
                            ch.remove(ly)
                            report.append(f'{label} m{mi + 1}: dropped extra lyric "{ly.findtext("text")}"'
                                          f' (kept "{pref[0].findtext("text")}")')
                for ly in lys:
                    for p in ly.findall('placement'):
                        ly.remove(p)
                        moved += 1
    if moved:
        report.append(f'{label}: {moved} lyric(s) moved from above to below the staff')


def fix_slurs(staff, label):
    """Remove slur starts/ends whose partner chord no longer carries the other end
    (a dangling start would otherwise pair with an unrelated later slur end)."""
    at = {}
    for mi, m in enumerate(staff.findall('Measure')):
        for t, el, d in timed(m.find('voice'), f'measure {mi + 1}'):
            if el.tag == 'Chord':
                at[(mi, t)] = el

    def ends(ch, side):
        return [sp for sp in ch.findall('Spanner') if sp.get('type') == 'Slur' and sp.find(side) is not None]

    def target(mi, t, sp, side):
        loc = sp.find(side).find('location')
        return mi + int(loc.findtext('measures') or 0), t + Fr(loc.findtext('fractions') or '0')

    for (mi, t), ch in at.items():
        for side, other in (('next', 'prev'), ('prev', 'next')):
            for sp in ends(ch, side):
                tgt = at.get(target(mi, t, sp, side))
                if tgt is None or not any(target(*k, o, other) == (mi, t)
                                          for k in [target(mi, t, sp, side)] for o in ends(tgt, other)):
                    ch.remove(sp)
                    report.append(f'{label} m{mi + 1} at {t}: removed slur {"start" if side == "next" else "end"}'
                                  ' with no matching partner')
                    continue
                loc = sp.find(side).find('location')
                for v in loc.findall('voices'):
                    loc.remove(v)


def fix_ties(staff, label):
    at = {}
    for mi, m in enumerate(staff.findall('Measure')):
        for t, el, d in timed(m.find('voice'), f'measure {mi + 1}'):
            if el.tag == 'Chord':
                at[(mi, t)] = el
    for (mi, t), ch in at.items():
        for si, n in enumerate(ch.findall('Note')):
            for sp in n.findall('Spanner'):
                if sp.get('type') != 'Tie':
                    continue
                side = sp.find('next') if sp.find('next') is not None else sp.find('prev')
                loc = side.find('location')
                dm = int(loc.findtext('measures') or 0)
                df = Fr(loc.findtext('fractions') or '0')
                tgt = at.get((mi + dm, t + df))
                ti = None
                if tgt is not None:
                    for k, x in enumerate(tgt.findall('Note')):
                        if x.findtext('pitch') == n.findtext('pitch'):
                            ti = k
                if ti is None:
                    n.remove(sp)
                    report.append(f'{label} m{mi + 1} at {t}, pitch {n.findtext("pitch")}: '
                                  f'removed tie ({side.tag}) with no matching note')
                    continue
                for c in list(loc):
                    loc.remove(c)
                for tag, val in (('measures', dm), ('fractions', df), ('notes', ti - si)):
                    if val:
                        ET.SubElement(loc, tag).text = str(val)


def set_name(part, name):
    part.find('trackName').text = name
    inst = part.find('Instrument')
    for tag in ('longName', 'shortName'):
        el = inst.find(tag)
        if el is not None:
            for c in list(el):
                el.remove(c)
            el.text = name


def split(root, staff_no, upper, lower, divisi):
    score = root.find('Score')
    if score.find('Excerpt') is not None or root.find('.//Excerpt') is not None:
        report.append('WARNING: file contains excerpts (parts); they are not updated')
    staves = score.findall('Staff')
    if not 1 <= staff_no <= len(staves):
        fail(f'staff {staff_no} does not exist (score has {len(staves)})')
    src = staves[staff_no - 1]

    # locate the part owning the staff
    parts, g, owner = score.findall('Part'), 0, None
    for p in parts:
        n = len(p.findall('Staff'))
        if g < staff_no <= g + n:
            owner = p
            if n != 1:
                fail('the staff belongs to a part with several staves; not supported')
        g += n

    U, L = build(src, 'U', divisi), build(src, 'L', divisi)
    fix_ties(U, 'upper')
    fix_ties(L, 'lower')
    fix_slurs(U, 'upper')
    fix_slurs(L, 'lower')

    idx = list(score).index(src)
    score.remove(src)
    score.insert(idx, U)
    score.insert(idx + 1, L)
    for i, st in enumerate(score.findall('Staff'), 1):
        st.set('id', str(i))

    # brackets that span the split staff grow by one
    g = 0
    for p in parts:
        for st in p.findall('Staff'):
            g += 1
            for b in st.findall('bracket'):
                span = int(b.get('span', '1'))
                if g <= staff_no < g + span and not (g == staff_no and span == 1):
                    b.set('span', str(span + 1))

    new = copy.deepcopy(owner)
    strip_eids(new)
    new.set('id', str(max(int(p.get('id')) for p in parts) + 1))
    st = new.find('Staff')
    for b in st.findall('bracket'):
        st.remove(b)
    used = {int(c.text) for c in score.iter('midiChannel')}
    free = next(c for c in range(16) if c not in used and c != 9)
    for ch in new.find('Instrument').findall('Channel'):
        mc = ch.find('midiChannel')
        if mc is not None:
            mc.text = str(free)
    set_name(owner, upper)
    set_name(new, lower)
    score.insert(list(score).index(owner) + 1, new)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('output')
    ap.add_argument('--staff', type=int, default=1, help='1-based staff number to split (default 1)')
    ap.add_argument('--upper-name', default='S')
    ap.add_argument('--lower-name', default='A')
    ap.add_argument('--divisi', choices=['upper', 'lower'], default='upper',
                    help='who gets the extra notes of 3+-note chords (default upper)')
    a = ap.parse_args()

    out_base = os.path.splitext(os.path.basename(a.output))[0]
    os.makedirs(os.path.dirname(os.path.abspath(a.output)), exist_ok=True)
    if a.input.lower().endswith('.mscx'):
        tree = ET.parse(a.input)
        split(tree.getroot(), a.staff, a.upper_name, a.lower_name, a.divisi)
        tree.write(a.output, encoding='UTF-8', xml_declaration=True)
    else:
        zin = zipfile.ZipFile(a.input)
        mscx = next(n for n in zin.namelist() if n.endswith('.mscx') and '/' not in n)
        root = ET.fromstring(zin.read(mscx))
        split(root, a.staff, a.upper_name, a.lower_name, a.divisi)
        data = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
        new_mscx = out_base + '.mscx'
        with zipfile.ZipFile(a.output, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename == mscx:
                    zout.writestr(new_mscx, data)
                elif info.filename == 'META-INF/container.xml':
                    zout.writestr(info.filename, zin.read(info.filename).decode('utf-8')
                                  .replace(f'"{mscx}"', f'"{new_mscx}"'))
                else:
                    zout.writestr(info, zin.read(info.filename))
    print('\n'.join(report) if report else 'No special cases.')
    print(f'Wrote {a.output}')


if __name__ == '__main__':
    main()
