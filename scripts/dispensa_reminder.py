#!/usr/bin/env python3
"""Promemoria serale Dispensa.

Manda una notifica push (via ntfy) se durante il giorno appena concluso NON e'
stato aggiornato nulla nell'app Dispensa. "Aggiornato" = aggiunto un alimento
(frigo/freezer/dispensa), salvato un menu, o importato uno scontrino.

Le rimozioni non lasciano traccia nel database, quindi non vengono rilevate: se
in un giorno hai solo tolto roba senza aggiungere niente, la notifica parte
comunque.

Lo script viene lanciato da .github/workflows/dispensa-reminder.yml verso
mezzanotte (ora italiana).
"""
import datetime
import json
import os
import sys
import urllib.request
from zoneinfo import ZoneInfo

# Ora locale (Italia) a cui deve partire il promemoria.
SEND_HOUR = 22

# Canale ntfy a cui e' iscritto il telefono (vedi app "ntfy").
NTFY_TOPIC = "dispensa-elena-4b90bc88"
NTFY_URL = "https://ntfy.sh/" + NTFY_TOPIC

# Chiave client pubblica del progetto Firebase di produzione: e' gia' visibile in
# index.html, non e' un segreto. Serve solo per farsi dare un token anonimo.
API_KEY = "AIzaSyCOljfd-EERukLj552ThoMxe0NmflGibYs"
BASE = "https://freezer-3960e-default-rtdb.firebaseio.com"


def firebase_anon_token():
    req = urllib.request.Request(
        "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=" + API_KEY,
        data=b'{"returnSecureToken":true}',
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["idToken"]


def read_node(path, token):
    url = BASE + "/" + path + ".json?auth=" + token
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.load(resp) or {}


def find_activity(token, target):
    """Restituisce una breve descrizione dell'attivita' trovata, o None."""
    for node in ("fridge_items", "freezer_items", "pantry_items"):
        items = read_node(node, token)
        if any(isinstance(v, dict) and v.get("entryDate") == target
               for v in items.values()):
            return "nuovo alimento in " + node

    meal_plan = read_node("meal_plan", token)
    if isinstance(meal_plan, dict) and str(meal_plan.get("savedAt", "")).startswith(target):
        return "menu salvato"

    queue = read_node("fridge_queue", token)
    if any(isinstance(v, dict) and str(v.get("acquiredAt", "")).startswith(target)
           for v in queue.values()):
        return "scontrino importato"

    return None


def send_reminder():
    msg = "Hai aggiornato la Dispensa oggi? Controlla se devi inserire o togliere qualcosa."
    req = urllib.request.Request(
        NTFY_URL,
        data=msg.encode("utf-8"),
        headers={"Title": "Promemoria Dispensa", "Tags": "shopping_cart"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def main():
    now = datetime.datetime.now(ZoneInfo("Europe/Rome"))

    # Il workflow schedulato parte a due orari UTC (uno per l'ora legale, uno per
    # l'ora solare): proseguiamo solo in quello che in Italia corrisponde alle
    # SEND_HOUR. Le esecuzioni manuali (workflow_dispatch) passano sempre.
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and now.hour != SEND_HOUR:
        print("In Italia sono le " + now.strftime("%H:%M") + " - non sono le "
              + str(SEND_HOUR) + ", nessuna azione.")
        return

    # Giorno da controllare: dopo mezzogiorno = oggi, prima = ieri (cosi' funziona
    # sia di sera sia se un'esecuzione manuale capita dopo mezzanotte).
    day = now if now.hour >= 12 else now - datetime.timedelta(days=1)
    target = day.strftime("%Y-%m-%d")

    token = firebase_anon_token()
    activity = find_activity(token, target)

    if activity:
        print("Attivita' registrata il " + target + " (" + activity + ") - nessuna notifica.")
        return

    send_reminder()
    print("Nessuna attivita' il " + target + " - notifica inviata.")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:  # noqa: BLE001
        print("ERRORE: " + repr(err), file=sys.stderr)
        sys.exit(1)
