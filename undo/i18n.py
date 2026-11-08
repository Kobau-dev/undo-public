"""On-screen text. English by default; UNDO_LANG=fr switches it to French. The source strings are the English ones."""
from __future__ import annotations

import os

FR = {
    # bubble
    "Listening…": "Je t'écoute…",
    "Transcribing…": "Je transcris…",
    "Got it": "J'ai compris",
    "Thinking…": "Je réfléchis…",
    "I know what to do": "J'ai trouvé quoi faire",
    "Working on it…": "Je remets tout en place…",
    "Done": "Terminé",
    "Failed": "Échec",
    "Stopped": "Arrêté",
    "Undo is ready": "Undo est prêt",
    "Esc to quit": "Échap pour quitter",
    "Hands off · Esc": "Ne touche à rien · Échap",
    "Hands off, I'm on it": "Ne touche à rien, je m'occupe de tout",
    "Or type here…": "Ou tape ici…",
    "Press Enter to send": "Entrée pour envoyer",
    # the request
    "What do you want back?": "Qu'est-ce que tu veux récupérer ?",
    "Speak now: say what you want back, then press Enter to send.": "Parle maintenant : dis ce que tu veux récupérer, puis Entrée pour envoyer.",
    "Say what you want back… or type it here and press Enter": "Dis ce que tu veux récupérer… ou tape-le ici puis Entrée",
    "I didn't hear anything. What do you want back?": "Je n'ai rien entendu. Qu'est-ce que tu veux récupérer ?",
    "Couldn't transcribe that. What do you want back?": "Transcription impossible. Qu'est-ce que tu veux récupérer ?",
    "Transcribing (Gladia)…": "Transcription (Gladia)…",
    "Cancelled.": "Annulé.",
    "Nothing heard.": "Rien entendu.",
    "Undo is listening…  ": "Undo écoute…  ",
    "Speak, or type your request and press Enter  ·  Esc to close": "Parle, ou tape ta demande puis Entrée  ·  Échap pour fermer",
    # the run
    "Recording ({minutes} min). Press {hotkey} and say what you want back.": "Enregistrement actif ({minutes} min). Appuie sur {hotkey} et dis ce que tu veux récupérer.",
    "Press {hotkey} and say what you want back.": "Appuie sur {hotkey} et dis ce que tu veux récupérer.",
    "Going through the last {minutes} minutes…": "Je relis les {minutes} dernières minutes…",
    "Strategy: {strategy}": "Stratégie : {strategy}",
    "Strategy: {strategy} · confidence {confidence}": "Stratégie : {strategy} · confiance {confidence}",
    "I'm only {confidence} sure. Try anyway?": "Je ne suis sûr qu'à {confidence}. Je tente quand même ?",
    "Emergency stop (Esc).": "Arrêt d'urgence (Échap).",
    "Stopped by the user (Esc)": "Arrêté par l'utilisateur (Échap)",
    "Loop detected: “{action}” repeated {n} times": "Boucle détectée : « {action} » répété {n} fois",
    "No answer to: {question}": "Pas de réponse à : {question}",
    "Maximum number of steps reached": "Nombre maximal d'étapes atteint",
    "refused: password field": "refus : champ mot de passe",
    "Sensitive action: {action}. Continue?": "Action sensible : {action}. Continuer ?",
    "stopped before saving / sending": "arrêt avant l'enregistrement / l'envoi",
    "{n} values restored from history": "{n} valeurs remises depuis l'historique",
    "H agent (holo-desktop) running…": "Agent H (holo-desktop) en cours…",
    # console and Tk overlay
    "Ready": "Prêt",
    "Heard": "J'ai entendu",
    "Going through the recording…": "Analyse de l'enregistrement…",
    "Understood": "J'ai compris",
    "Taking over": "Je reprends la main",
    "no terminal to confirm → refused": "pas de terminal pour confirmer → refusé",
    "no terminal to answer": "pas de terminal pour répondre",
    # menu bar
    "Pause recording": "Pause de l'enregistrement",
    "Start Undo": "Démarrer Undo",
    "Stop Undo": "Arrêter Undo",
    "Buffer length": "Durée du buffer",
    "Quit": "Quitter",
}


def t(text: str, **values) -> str:
    """`text` in the on-screen language, with its {placeholders} filled in."""
    if os.environ.get("UNDO_LANG", "en").strip().lower().startswith("fr"):
        text = FR.get(text, text)
    return text.format(**values) if values else text
