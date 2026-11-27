# Fakturafalter 0.9.11.1

CSV / XML / PDF rein. ZUGFeRD raus. Lokal geprüft.

Korrektur zum Block-Assistenten aus 0.9.11: Spalten werden im Eingang je Block
gegen dessen eigene Kopfzeile gelesen, Festwerte (etwa EUR) stoßen sich nicht
mit einer Spalte, und Abweichungsmeldungen nennen den freien Blocknamen.
Vorheriger Stand: 0.9.11.

## Was sich ändert

- **Spalten je Block im Eingang:** Der Eingang und die Probe-Liste nutzen
  dieselben `bloecke[].felder` gegen die jeweilige Block-Kopfzeile wie die
  Sichtseiten-Vorschau im Assistenten. Pflichtfelder wie Belegname oder
  Bezeichnung werden nicht mehr gegen die erste Kopfzeile der Datei geprüft.
  Ein in 0.9.11 gespeichertes Blockprofil wird nach dem Update weiter geladen,
  auch wenn zwei normale Blöcke noch typ `kopf` tragen: die Zuordnung läuft
  über id und Kopfzeile.

- **Währung:** Ein festes EUR, das der Assistent früher in mehrere Blöcke
  geschrieben hat, ist nur noch ein Fallback, wenn die Spalte leer ist. Eine
  Spalte hat Vorrang. `€` und `EUR` gelten als dieselbe Währung. Neue Profile
  setzen festes BT-3/BT-5 nicht mehr in jeden Block.

- **Meldungen:** Weicht ein Feld zwischen zwei Blöcken ab, steht der freie
  Blockname (oder die id) in der Meldung, nicht zweimal typ „kopf“.

- **Einheit:** Ist die Einheitsspalte zugeordnet, bleibt sie erhalten. Die
  Warnung „Einheit fehlte, Stück angenommen“ erscheint nur bei wirklich leerer
  Zelle und eingeschaltetem Schalter „Fehlende Einheit = Stück verwenden“.

## Prüfung

Lokal: Assistent → YAML schreiben → Profil neu laden → Eingang (fiktive Datei
mit `#Kopf`/`#Beleg` in der Satzart-Spalte, getrennte normale Blöcke mit eigener
Kopfzeile); Probe-Liste, Sichtseiten-Lesen und Eingang dasselbe Ergebnis;
älteres typ-`kopf`-Profil ohne Neu-Einrichtung; `€` gegen fest EUR ohne
Abweichung; Einheit nur bei leerer Zelle.

## Credits

Konzept und Idee: deciderino. Code: geschrieben von der KI Grok Bot.
