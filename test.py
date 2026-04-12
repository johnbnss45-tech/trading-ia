import yfinance as yf
import openai
import time
import json
import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

# Configuration - remplace par tes vraies valeurs
CLE_API = "REMPLACEZ_PAR_VOTRE_CLE"
EMAIL = "jhnnnsn45@gmail.com"
MOT_DE_PASSE_EMAIL = "mrsyeabjcpsubphc"

openai.api_key = CLE_API

actions = ["NVDA", "AAPL", "TSLA", "MSFT", "AMZN", "GOOGL", "META", "AMD"]

def envoyer_email(sujet, contenu):
    print("Email desactive pour l'instant")
    try:
        msg = MIMEText(contenu, 'plain', 'utf-8')
        msg['Subject'] = sujet
        msg['From'] = EMAIL
        msg['To'] = EMAIL
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as serveur:
            serveur.login(EMAIL, MOT_DE_PASSE_EMAIL)
            serveur.send_message(msg)
        print("Email envoye !")
    except Exception as e:
        print(f"Erreur email : {e}")

def sauvegarder(decisions):
    try:
        with open("historique.json", "r") as f:
            historique = json.load(f)
    except:
        historique = []
    historique.append(decisions)
    with open("historique.json", "w") as f:
        json.dump(historique, f, indent=2, ensure_ascii=False)
    print("Decisions sauvegardees !")

def analyser_marche():
    maintenant = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    print(f"\n{'='*50}")
    print(f"Analyse lancee a {maintenant}")
    print(f"{'='*50}\n")

    donnees = []

    for symbole in actions:
        try:
            action = yf.Ticker(symbole)
            info = action.history(period="5d")
            prix_actuel = float(info['Close'].iloc[-1])
            prix_hier = float(info['Close'].iloc[-2])
            variation = ((prix_actuel - prix_hier) / prix_hier) * 100
            ligne = f"{symbole} : {prix_actuel:.2f}$ ({variation:+.2f}%)"
            donnees.append(ligne)
            print(ligne)
        except Exception as e:
            print(f"Erreur pour {symbole} : {e}")

    donnees_texte = "\n".join(donnees)

    reponse = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": f"""Tu es un trader expert. Voici les donnees du marche :

{donnees_texte}

Pour chaque action, reponds EXACTEMENT sous ce format :
SYMBOLE : ACHETE/VEND/ATTEND | Confiance: X/10 | raison courte"""}
        ]
    )

    resultat = reponse.choices[0].message.content
    print("\n=== Decisions de l'IA ===")
    print(resultat)

    sauvegarder({
        "date": maintenant,
        "donnees": donnees,
        "decisions": resultat
    })

    envoyer_email(
        f"Rapport Trading {maintenant}",
        f"DONNEES:\n{donnees_texte}\n\nDECISIONS:\n{resultat}"
    )

    print(f"\nProchaine analyse dans 30 minutes...")

while True:
    analyser_marche()
    time.sleep(1800)