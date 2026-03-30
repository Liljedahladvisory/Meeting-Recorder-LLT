# Meeting Recorder
**Liljedahl Advisory AB**

Spelar in möten, transkriberar i realtid och genererar strukturerade mötesanteckningar med Claude AI. Primärt avsedd att användas vid fysiska möten, men fungerar utmärkt vid digitala möten. Inspelning sker genom mikrofon (inbyggd eller extern).

---

## Funktioner

- **Realtidstranskription** via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — transkriberar i bakgrunden medan mötet pågår
- **Talarseparation** via [pyannote.audio](https://github.com/pyannote/pyannote-audio) — märker upp vem som säger vad
- **Mötesanteckningar** genereras automatiskt av Claude (sammanfattning, beslut, action points)
- **Ljudkälla** — mikrofon
- **Exportera** transkript + anteckningar till Markdown, Word eller PDF.

---

## Krav

```
pip install faster-whisper pyannote.audio sounddevice numpy anthropic
```



### API-nycklar

| Nyckel | Var | Används till |
|--------|-----|--------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Generera mötesanteckningar |
| `HF_TOKEN` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) | Talarseparation (valfritt) |

Sätt dem som miljövariabler eller fyll i API-nyckeln direkt i appen:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export HF_TOKEN="hf_..."
```

---

## Användning

```bash
python meeting_recorder.py
```

1. Fyll i **mötetitel** och **deltagare** (kommaseparerade)
2. Välj **ljudkälla** — Mikrofon, iPhone-mikrofon etc
3. Välj **Whisper-modell** — Small (snabb) / Medium (balanserad) / Large v3 (bäst kvalitet)
4. Klicka **Starta inspelning**
5. Klicka **Avsluta möte** när mötet är slut — transkription av kvarvarande ljud fortsätter i bakgrunden
6. Klicka **Generera anteckningar** när transkriptionen är klar
7. Klicka **Spara** för att exportera till Markdown

---

## Ändringslogg

### Asynkron transkription och "Avsluta möte"-knapp
**Problem:** Transkriptionen blockerade inspelningsloopen — varje 20-sekunders ljudchunk väntade på att den föregående var klar innan nästa spelades in. För ett 30-minuters möte innebar det ~15 minuters väntetid efter att mötet avslutats.

**Lösning:** Ljudinspelning och transkription körs nu i separata trådar via en kö. Inspelningsloopen lägger chunks i kön och fortsätter direkt; en dedikerad worker-tråd transkriberar i bakgrunden. Statusfältet visar hur många delar som återstår.

Stoppknappen döptes om till **"Avsluta möte"** och stoppar *enbart* ljudinspelningen — transkription av redan inspelat ljud fullföljs ostört. "Generera anteckningar" låses upp automatiskt när allt är klart.

---

### Fungerande talarseparation
**Problem:** pyannote-pipelinen laddades in men anropades aldrig under transkriptionen. Talarseparation skedde alltså inte alls i praktiken.

**Lösning:** `_diarize()` anropas nu efter varje Whisper-transkription och producerar märkt utdata i transkriptvyn:

```
**SPEAKER_00:** Jag tycker att vi bör gå vidare med förslaget.
**SPEAKER_01:** Håller med, men vi behöver kolla budgeten först.
```

Kräver att `HF_TOKEN` är satt och att du accepterat villkoren för [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) på Hugging Face.

---

### Word-level talaralignering (WhisperX-metoden)
**Problem:** Den ursprungliga implementationen matchade varje Whisper-segment (5–10 sekunder) mot en enda talare via segmentets mittpunkt. Talarskiften *inuti* ett segment missades helt.

**Lösning:** Aligneringen sker nu på **ordnivå**. Whisper returnerar en tidsstämpel per ord (`word_timestamps=True`); varje ord matchas individuellt mot den pyannote-tur som täcker ordets mittpunkt. Ord som hamnar i tystnadsgap mellan turer tilldelas den *närmaste* turen istället för att märkas som "OKÄND".

Dessutom skickas antalet deltagare (räknat från Deltagare-fältet) till pyannote som `num_speakers`-ledtråd, vilket begränsar modellens sökutrymme och förbättrar precisionen mätbart i möten med känt deltagarantal.

---

### Whisper-modellväljare
**Problem:** Appen använde alltid Large v3, som är ~3× långsammare än Medium på CPU utan märkbar skillnad för konversationsljud på svenska.

**Lösning:** Ny kontroll i Konfiguration låter dig välja Small / Medium / Large v3 per session. Standard är **Medium**. Modellen laddas om automatiskt om du byter mellan sessioner.

---

## Licens

Internt verktyg — Liljedahl Advisory AB
