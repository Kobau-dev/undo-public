# Demo scenarios

After ⇧ ⇧, what you say lands in the bubble's text field. In every scenario, whether you speak or type, **Enter** sends the request and **Esc** cancels it.

The film follows three examples: undo (Blender, section 8), recover (CRM, section 7) and reuse (Mail then SignalConso, section 0). The last one is the easiest to try yourself, and nobody made a mistake in it: Undo fetches something seen earlier and uses it now.

## 0. Main scenario, reuse — real Mail → real SignalConso

1. `open demo/parcel.eml`: the Maison du Lit order email opens in the Mail app (just a file, nothing is sent or added to your accounts). Read it for a few seconds.
2. In the browser, on https://signal.conso.gouv.fr/en: "Online purchases" → order never delivered → website `www.maisondulit-exemple.fr`, up to the **Description** step (empty).
3. ⇧ ⇧, then say or type: "In the description, explain that my order never arrived, with the order number, date, item, amount and parcel tracking from this morning's email." Press Enter.

Expected: order number MDL-20261018-4472, October 18, 2026, the "Nuage" mattress, €389.00 and Colis Express tracking CE-77-4410-928 written in the description, in ~25 s. Undo stops there: no report is sent.

---

Local web mini-apps (static HTML/JS, no dependencies) + a bonus scenario on a native app. The pages themselves are in French, so their labels are quoted as they appear on screen.
Start the server: `python -m undo demo` → http://localhost:8765. The pages imitate real sites, with no visible demo buttons. Hidden commands: **Ctrl+Shift+E** expires the session, **Ctrl+Shift+R** resets the page (the notes page keeps its **Réinitialiser** button). `?t=90` shortens the session to 90 s (15 min by default).

Common prerequisites: `make run` is running (recorder active, shortcut armed); for the `python -m undo …` and `pip …` commands, activate the venv (`source .venv/bin/activate`); the browser is on the main screen,
the Undo overlay is visible. Speak in English or French, 1 to 2 sentences.

---

## 1. Lost form — `form.html`

**What the human does**
1. Open http://localhost:8765/form.html. A blue banner shows "Session active — expire dans 2:00".
2. Fill in the fields at a relaxed pace (30 to 60 s), for example:
   - Nom: `Dupont` — Prénom: `Marie`
   - Date de naissance: `14/03/1988` — Email: `marie.dupont@exemple.fr`
   - Adresse: `12 rue des Lilas, 75011 Paris`
   - Objet: `Renouvellement de passeport`
   - Motif: `Passeport perdu lors d'un déplacement à Lyon le 2 octobre. Déclaration de perte n° 2026-LY-0481 jointe.`
   - Pièces: `Déclaration de perte, justificatif de domicile, photo d'identité`
3. Press **Ctrl+Shift+E** (or wait for the session to end). All the fields empty, red banner.
4. Press **⇧ ⇧ (two quick taps on Shift)** and say, then press Enter:

> "I lost the whole form I had filled in, the session expired, put back everything I typed."

**Expected result**
- Overlay: *your request in the bubble → Enter → analysis → "I understood: the form was emptied… strategy: manual_redo"*.
- The agent clicks field by field and retypes the exact values (including the select and the two text areas).
- It stops **before** "Envoyer la demande": the safeguard blocks any click on Send/Save/Pay that was not requested.
- Target duration: < 90 s.

---

## 2. Forgotten setting — `settings.html`

**What the human does**
1. Open http://localhost:8765/settings.html. Green banner "Tout fonctionne".
2. Change several settings over 20–30 s, in this order:
   - Filigrane → ON (harmless)
   - Résolution → `3840×2160 (4K)` (harmless)
   - Sortie HDR → ON → **the banner turns red**: "Le HDR n'est pas supporté avec le codec H.264"
   - Keep going: Normalisation audio → OFF (harmless, after the error)
3. Press **⇧ ⇧ (two quick taps on Shift)** and say, then press Enter:

> "Something broke the export, I can't remember which setting I changed, put back the one that caused the error."

**Expected result**
- The analysis identifies that the error appeared right after **Sortie HDR** was turned on and proposes turning it off (or switching the codec to H.265).
- The agent only clicks the HDR toggle. Filigrane, 4K and Normalisation audio stay as the user left them (selective undo).
- The banner turns green again.

---

## 3. Deleted content — `notes.html`

**What the human does**
1. Open http://localhost:8765/notes.html (5 pre-filled notes).
2. Mark "Réserver la salle pour la rétro" as not done then done again (noise), add a note `Appeler le comptable`.
3. Delete **"Relancer le fournisseur pour la facture #4521"** (Supprimer button). It goes to the trash.
4. Keep working for 20 s: add a note `Commander les goodies`, mark "Lire le rapport d'incident" as done.
5. Press **⇧ ⇧ (two quick taps on Shift)** and say, then press Enter:

> "I deleted the note about the supplier's invoice by mistake, put it back."

**Expected result**
- Strategy chosen: **trash** (the analysis sees the Corbeille section).
- The agent clicks **Restaurer** next to the right note, and only that one. The notes added after the deletion stay.
- Variant (universal fallback): click **Vider la corbeille** first, before calling Undo → the agent has to recreate the note by hand (`manual_redo`) with the exact title and text read from the recording.

---

## 4. Lost report — `crm.html`

1. Fill in the record (company, contact, amount, stage, long report, next steps).
2. **Ctrl+Shift+E**: the session expires and everything is erased.
3. ⇧ ⇧: "My CRM session expired and I lost my report, put back everything I wrote." Press Enter.

Expected: all the fields retyped, without clicking "Enregistrer".

## 5. From one app to another — `mail.html` (Safari) → `claim.html` (Brave)

1. Open `claim.html` in Brave (empty), then read `mail.html` in **Safari** for a few seconds.
2. Go back to Brave, ⇧ ⇧: "Fill in this form with the claim number, the date, the amount and the expert's reference from the insurance email." Press Enter.

Expected: SIN-2026-07731, 28/10/2026, 1840, EXP-55120 copied from the email, without clicking "Envoyer".

### Real Mail app version

`open demo/sinistre.eml` opens the same email in the Mail app (just a file: nothing is sent or added to your accounts). Keep it visible for a few seconds, open http://localhost:8765/claim.html in Brave, then ⇧ ⇧: "fill in the form with the details from the insurance email", and press Enter.

---

## 6. Native app bonus — TextEdit / Notes

1. Open TextEdit (⌘N), type 4–5 lines of text, for example short meeting notes.
2. Close the window (⌘W) → **Delete** (do not save).
3. Press **⇧ ⇧ (two quick taps on Shift)** and say, then press Enter:

> "I closed my TextEdit document without saving it, retype what I wrote."

**Expected result**: the agent opens TextEdit (`open_app`), creates a new document (⌘N) and retypes the text read by OCR, line breaks included.

---

## 7. Lost report in a real desktop app — Sillage CRM (`demo/crm_app`)

Native desktop application (PySide6 / Qt, outside the browser): CRM for a medical sales representative at "Laboratoires Delmas"
(dashboard, contacts, accounts, opportunities, activities, reports, contact record, "Nouveau compte rendu
de visite" form). Nothing is saved until you click **Enregistrer le compte rendu** (no draft). Follows the
Mac's light / dark mode. Each field has a visible label and the same accessibility name, so `undo/ax.py` sees
`«Compte rendu de la visite»`, `«Prochaine étape»`, the product checkboxes, the visit type radio buttons, etc.

```bash
pip install -e ".[crm]"                                         # PySide6
python -m demo.crm_app --contact marchand --session-timeout 600  # or: make crm
python -m demo.crm_app --contact marchand --new-report --session-timeout 90 --session-absolute
```

Options: `--session-timeout S` (seconds of **inactivity** before expiry, 300 by default, 0 = never, or
`SILLAGE_SESSION_TIMEOUT`), `--session-absolute` (counts from login even while you type — handy for a timed
take), `--contact <name|id>` (opens the record), `--new-report` (opens the form; with `--contact`, account and
contact are pre-filled as when you start from the record), `--page contacts|comptes|…`, `--theme light|dark`,
`--size 1440x900`. Hidden command: **⌃⇧E** (or **⌘⇧E**) expires the session immediately.

**What the human does**
1. Run `python -m demo.crm_app --contact marchand`, click **Nouveau compte rendu de visite** on Dr Hélène Marchand's record.
2. Fill in: time `12:45`, duration `20 min`, type **Face-à-face**, objective `Suivi de prescription`, tick Tensiora and
   Glycalm LP, documentation handed over, a long report (several paragraphs), needs / objections, next step,
   follow-up date `01/12/2026`, the "Ajouter un rappel dans mon agenda" checkbox.
3. **⌃⇧E** (or wait for the expiry): sheet "Votre session a expiré, veuillez vous reconnecter". Log back in
   (any non-empty password): the form is back empty, the report is lost.
4. ⇧ ⇧: "My session expired and I lost my whole visit report, put back everything I entered." Press Enter.

Expected: every field, checkbox and radio button put back, without clicking "Enregistrer le compte rendu".

---

## 8. Blender — architect's villa, pool deleted too early (`demo/blender`)

Undo goes back in time in Blender (⌘Z ×6), copies the pool deleted by mistake, returns to the present (⇧⌘Z ×8) and
pastes it back in place, without losing the work done since. Automatically replayed scene, prepared instructions, take
script: see [`demo/blender/README.md`](blender/README.md).

---

## Testing without redoing the demo

- `python -m undo analyze --replay recordings/form-lost "restore the form"`: reruns only the Analyzer on a saved recording (`python -m undo export recordings/form-lost` right after a demo to create it).
- `python -m undo run --dry-run`: the agent prints its actions instead of executing them.
