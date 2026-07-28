#!/usr/bin/env python3
"""Baut BWL-Trainer.html aus app_template.html + fragen_single.json (+ fragen_multi.json)."""
import json, os, sys, re

BASE = os.path.dirname(os.path.abspath(__file__))
def p(n): return os.path.join(BASE, n)

fragen = []
with open(p('fragen_single.json'), encoding='utf-8') as fh:
    fragen += json.load(fh)
for extra in ('fragen_multi.json', 'fragen_schwer.json'):
    if os.path.exists(p(extra)):
        with open(p(extra), encoding='utf-8') as fh:
            fragen += json.load(fh)

# Identische Fragetexte gehoeren zu einer Familie, auch wenn Antwortsets und
# Schwierigkeit variieren. So erscheint dieselbe Frage nie doppelt in einer Runde.
textgruppen = {}
for q in fragen:
    key = re.sub(r'\s+', ' ', q['frage']).strip().casefold()
    textgruppen.setdefault(key, []).append(q)
duplikatgruppen = 0
for nr, gruppe in enumerate((g for g in textgruppen.values() if len(g) > 1), 1):
    familie = next((q.get('familie') for q in gruppe if q.get('familie')), None)
    familie = familie or 'gleicher-fragetext-%02d' % nr
    for q in gruppe:
        q['familie'] = familie
    duplikatgruppen += 1

# IDs neu und stabil vergeben, Struktur prüfen
fehler = []
for i, q in enumerate(fragen, 1):
    q['id'] = 'q%03d' % i
    # Die Auswahl wird zentral in auswahl.json gepflegt; alte Markierungen in
    # den Quelldateien duerfen das Ergebnis nicht unbemerkt beeinflussen.
    q.pop('essential', None)
    q.pop('wiederholung', None)
    opts = q['optionen']
    if len(opts) != len(set(opts)):
        fehler.append((q['id'], 'doppelte Antwortoption'))
    if not (4 <= len(opts) <= 10):
        fehler.append((q['id'], '%d Antwortoptionen (erlaubt 4-10)' % len(opts)))
    if isinstance(q['richtig'], list):
        if not (2 <= len(q['richtig']) <= 5):
            fehler.append((q['id'], 'Mehrfachfrage mit %d richtigen' % len(q['richtig'])))
        if len(q['richtig']) >= len(opts):
            fehler.append((q['id'], 'alle Optionen als richtig markiert'))
        if any(not (0 <= r < len(opts)) for r in q['richtig']):
            fehler.append((q['id'], 'Index ausserhalb der Optionen'))
        if len(set(q['richtig'])) != len(q['richtig']):
            fehler.append((q['id'], 'doppelter Index'))
    else:
        if not (0 <= q['richtig'] < len(opts)):
            fehler.append((q['id'], 'Index ausserhalb der Optionen'))
    if q['schwierigkeit'] not in ('leicht', 'mittel', 'schwer'):
        fehler.append((q['id'], 'unbekannte Schwierigkeit'))
    for feld in ('frage', 'erklaerung', 'thema'):
        if not str(q.get(feld, '')).strip():
            fehler.append((q['id'], 'leeres Feld: ' + feld))

# Kuratierter Kern und vollstaendiger Wiederholungsstoff. Bereiche halten die
# deutlich groessere 230er-Auswahl lesbar; die App erhaelt konkrete Flags.
auswahl_file = p('auswahl.json')
if not os.path.exists(auswahl_file):
    fehler.append(('Auswahl', 'auswahl.json fehlt'))
else:
    with open(auswahl_file, encoding='utf-8') as fh:
        auswahl = json.load(fh)

    def id_num(qid):
        if not re.fullmatch(r'q\d{3}', str(qid)):
            raise ValueError('ungueltige ID %r' % qid)
        return int(qid[1:])

    essential_ids = set(auswahl.get('essential', []))
    wiederholung_ids = set()
    try:
        for start, ende in auswahl.get('wiederholung_bereiche', []):
            start_num, ende_num = id_num(start), id_num(ende)
            if start_num > ende_num:
                raise ValueError('Bereich %s bis %s ist rueckwaerts' % (start, ende))
            wiederholung_ids.update('q%03d' % nr for nr in range(start_num, ende_num + 1))
    except (TypeError, ValueError) as exc:
        fehler.append(('Auswahl', str(exc)))

    bekannte_ids = {q['id'] for q in fragen}
    unbekannt = (essential_ids | wiederholung_ids) - bekannte_ids
    if unbekannt:
        fehler.append(('Auswahl', 'unbekannte IDs: ' + ', '.join(sorted(unbekannt))))
    if len(essential_ids) != 81:
        fehler.append(('Auswahl', 'Essential muss 81 Fragen enthalten, gefunden: %d' % len(essential_ids)))
    if len(wiederholung_ids) != 230:
        fehler.append(('Auswahl', 'Wiederholung muss 230 Fragen enthalten, gefunden: %d' % len(wiederholung_ids)))
    if not essential_ids <= wiederholung_ids:
        fehler.append(('Auswahl', 'Essential muss vollstaendig in Wiederholung enthalten sein'))

    for q in fragen:
        if q['id'] in essential_ids:
            q['essential'] = True
        if q['id'] in wiederholung_ids:
            q['wiederholung'] = True

# Fachhinweise bleiben getrennt vom Vorlesungsinhalt. So kann die App die
# Prüfungsantwort zeigen und fachliche Abweichungen sichtbar kennzeichnen.
hinweis_file = p('fachhinweise.json')
if os.path.exists(hinweis_file):
    with open(hinweis_file, encoding='utf-8') as fh:
        hinweis_gruppen = json.load(fh)
    fragen_nach_id = {q['id']: q for q in fragen}
    verwendete_ids = set()
    for gruppe in hinweis_gruppen:
        ids = gruppe.get('ids', [])
        hinweis = {
            k: gruppe[k] for k in ('hinweis', 'quelle', 'url')
            if str(gruppe.get(k, '')).strip()
        }
        if not ids:
            fehler.append(('Fachhinweis', 'Gruppe ohne IDs'))
        if not hinweis.get('hinweis'):
            fehler.append((', '.join(ids) or 'Fachhinweis', 'Hinweistext fehlt'))
        for qid in ids:
            if qid in verwendete_ids:
                fehler.append((qid, 'mehrfacher Fachhinweis'))
            elif qid not in fragen_nach_id:
                fehler.append((qid, 'Fachhinweis verweist auf unbekannte Frage'))
            else:
                fragen_nach_id[qid]['fachhinweis'] = dict(hinweis)
                verwendete_ids.add(qid)

if fehler:
    print('ABBRUCH — Strukturfehler:', file=sys.stderr)
    for f in fehler:
        print('  ', f[0], f[1], file=sys.stderr)
    sys.exit(1)

daten = json.dumps(fragen, ensure_ascii=False, separators=(',', ':'))
# </script> im Inhalt würde den JSON-Block vorzeitig schliessen
daten = daten.replace('</', '<\\/')

# Reaction-GIFs bleiben als eigene, leicht prüfbare Datenquelle getrennt vom
# Fragenkatalog. Der Build akzeptiert nur direkte GIPHY-Mediendateien.
meme_file = p('meme_daten.json')
if not os.path.exists(meme_file):
    print('ABBRUCH — meme_daten.json fehlt', file=sys.stderr)
    sys.exit(1)
with open(meme_file, encoding='utf-8') as fh:
    memes = json.load(fh)
meme_fehler = []
meme_terms = set()
meme_urls = set()
for i, meme in enumerate(memes, 1):
    for feld in ('term', 'url', 'title', 'caption'):
        if not str(meme.get(feld, '')).strip():
            meme_fehler.append(('Meme %d' % i, 'leeres Feld: ' + feld))
    term = str(meme.get('term', '')).casefold()
    url = str(meme.get('url', ''))
    if term in meme_terms:
        meme_fehler.append(('Meme %d' % i, 'doppelter Begriff: ' + term))
    if url in meme_urls:
        meme_fehler.append(('Meme %d' % i, 'doppelte URL'))
    if not re.fullmatch(r'https://media\.giphy\.com/media/[A-Za-z0-9_-]+/giphy\.gif', url):
        meme_fehler.append(('Meme %d' % i, 'keine direkte GIPHY-GIF-URL'))
    meme_terms.add(term)
    meme_urls.add(url)
if meme_fehler:
    print('ABBRUCH — Meme-Datenfehler:', file=sys.stderr)
    for f in meme_fehler:
        print('  ', f[0], f[1], file=sys.stderr)
    sys.exit(1)
meme_daten = json.dumps(memes, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')

# Pflichtlektuere im Kommunismus-Modus. Marx starb 1883, der Text ist gemeinfrei;
# die Transkription der Erstausgabe stammt aus dem Deutschen Textarchiv.
kapital_file = p('kapital.json')
if not os.path.exists(kapital_file):
    print('ABBRUCH — kapital.json fehlt', file=sys.stderr)
    sys.exit(1)
with open(kapital_file, encoding='utf-8') as fh:
    kapital = json.load(fh)
kapital_eintraege = kapital.get('eintraege') if isinstance(kapital, dict) else None
kapital_fehler = []
if not isinstance(kapital_eintraege, list) or len(kapital_eintraege) < 100:
    kapital_fehler.append('braucht mindestens 100 Eintraege')
else:
    for nr, e in enumerate(kapital_eintraege, 1):
        if not isinstance(e, dict) or e.get('a') not in ('k', 's', 'p', 'x'):
            kapital_fehler.append('Eintrag %d: a muss k, s, p oder x sein' % nr)
            break
    if not any(e.get('a') == 'k' for e in kapital_eintraege):
        kapital_fehler.append('keine Kapitelueberschrift gefunden')
if not str(kapital.get('quelle', '')).strip():
    kapital_fehler.append('Quellenangabe fehlt')
if kapital_fehler:
    print('ABBRUCH — kapital.json:', file=sys.stderr)
    for f in kapital_fehler:
        print('  ', f, file=sys.stderr)
    sys.exit(1)
kapital_daten = json.dumps(kapital, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')

with open(p('app_template.html'), encoding='utf-8') as fh:
    tpl = fh.read()
for ph in ('__FRAGEN__', '__MEMES__', '__STILE__', '__KAPITAL__'):
    if ph not in tpl:
        print('ABBRUCH — Platzhalter %s fehlt in app_template.html' % ph, file=sys.stderr)
        sys.exit(1)

# Ein einziges Designsystem verhindert visuelle Abweichungen zwischen Ansichten.
style_file = p('editorial.css')
if not os.path.exists(style_file):
    print('ABBRUCH — editorial.css fehlt', file=sys.stderr)
    sys.exit(1)
with open(style_file, encoding='utf-8') as fh:
    stil_css = fh.read().strip()
if '@import' in stil_css or 'url(' in stil_css:
    print('ABBRUCH — editorial.css enthaelt @import oder url()', file=sys.stderr)
    sys.exit(1)
if '[data-style="editorial"]' not in stil_css:
    print('ABBRUCH — editorial.css ist nicht auf editorial gescopt', file=sys.stderr)
    sys.exit(1)

seite = (tpl
    .replace('__FRAGEN__', daten)
    .replace('__MEMES__', meme_daten)
    .replace('__KAPITAL__', kapital_daten)
    .replace('__STILE__', stil_css))
for ausgabe in ('BWL-Trainer.html', 'index.html'):
    with open(p(ausgabe), 'w', encoding='utf-8') as fh:
        fh.write(seite)

from collections import Counter
einfach = sum(1 for q in fragen if not isinstance(q['richtig'], list))
mehrfach = len(fragen) - einfach
familien = sum(1 for q in fragen if q.get('familie'))
essential = sum(1 for q in fragen if q.get('essential'))
wiederholung = sum(1 for q in fragen if q.get('wiederholung'))
fachhinweise = sum(1 for q in fragen if q.get('fachhinweis'))
print('BWL-Trainer.html und index.html gebaut')
print('  Fragen gesamt : %d  (%d einfach, %d mehrfach)' % (len(fragen), einfach, mehrfach))
print('  mit Familie   : %d' % familien)
print('  Text-Duplikate: %d Gruppen zusammengefuehrt' % duplikatgruppen)
print('  Optionen      :', dict(sorted(Counter(len(q['optionen']) for q in fragen).items())))
print('  Schwierigkeit :', dict(Counter(q['schwierigkeit'] for q in fragen)))
print('  Essential     : %d' % essential)
print('  Wiederholung  : %d' % wiederholung)
print('  Fachhinweise  : %d' % fachhinweise)
print('  Reaction-GIFs : %d' % len(memes))
print('  Kapital       : %d Eintraege (%d Kapitel), %.0f KB' % (
    len(kapital_eintraege),
    sum(1 for e in kapital_eintraege if e['a'] == 'k'),
    len(kapital_daten) / 1024))
print('  Themen        : %d' % len(set(q['thema'] for q in fragen)))
print('  Designsysteme : 1  (editorial)')
print('  Stil-CSS      : %.0f KB' % (len(stil_css) / 1024))
print('  Dateigroesse  : %.0f KB' % (os.path.getsize(p('index.html')) / 1024))
