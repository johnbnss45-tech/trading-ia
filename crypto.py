from binance.client import Client
from openai import OpenAI
import os
import time
import json
from datetime import datetime
import urllib.request
from dotenv import load_dotenv
load_dotenv()

try:
    ip = urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
    print(f"IP du serveur : {ip}")
except:
    pass

CLE_API_BINANCE = os.environ.get("CLE_API_BINANCE")
CLE_SECRETE_BINANCE = os.environ.get("CLE_SECRETE_BINANCE")
CLE_OPENAI = os.environ.get("CLE_OPENAI")

client_binance = Client(CLE_API_BINANCE, CLE_SECRETE_BINANCE)
client_openai = OpenAI(api_key=CLE_OPENAI)

BUDGET_PAR_POSITION = 15
STOP_LOSS_PCT = 0.95
TAKE_PROFIT_PCT = 1.10
TRAILING_STOP_PCT = 0.97
MAX_POSITIONS = 3
CRYPTOS_BLOQUEES_FILE = "bloquees.json"

CRYPTOS_SERIEUSES = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "MATICUSDT",
    "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT", "FILUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "INJUSDT", "SEIUSDT",
    "SUIUSDT", "TIAUSDT", "FETUSDT", "RENDERUSDT", "STXUSDT",
    "RUNEUSDT", "ONDOUSDT", "AAVEUSDT", "MKRUSDT", "SNXUSDT"
}

def charger_bloquees():
    try:
        with open(CRYPTOS_BLOQUEES_FILE) as f:
            return set(json.load(f))
    except:
        return set()

def sauvegarder_bloquees():
    with open(CRYPTOS_BLOQUEES_FILE, "w") as f:
        json.dump(list(CRYPTOS_BLOQUEES), f)

CRYPTOS_BLOQUEES = charger_bloquees()
positions_ouvertes = {}

def sauvegarder_positions():
    with open("positions.json", "w") as f:
        json.dump(positions_ouvertes, f, indent=2)

def charger_positions():
    global positions_ouvertes
    try:
        with open("positions.json", "r") as f:
            positions_ouvertes = json.load(f)
        print(f"Positions chargees : {list(positions_ouvertes.keys())}")
    except:
        positions_ouvertes = {}

def get_prix(symbole):
    ticker = client_binance.get_ticker(symbol=symbole)
    return float(ticker['lastPrice'])

def scanner_opportunites():
    print("Scan du marche...")
    tous = client_binance.get_ticker()
    usdt = [
        t for t in tous
        if t['symbol'] in CRYPTOS_SERIEUSES
        and float(t['quoteVolume']) > 5000000
        and float(t['priceChangePercent']) > 0
        and t['symbol'] not in CRYPTOS_BLOQUEES
    ]
    top = sorted(usdt, key=lambda x: float(x['priceChangePercent']), reverse=True)[:8]
    return [t['symbol'] for t in top]

def get_donnees(symbole):
    try:
        ticker = client_binance.get_ticker(symbol=symbole)
        prix = float(ticker['lastPrice'])
        variation_24h = float(ticker['priceChangePercent'])
        volume = float(ticker['quoteVolume'])

        bougies = client_binance.get_klines(
            symbol=symbole,
            interval=Client.KLINE_INTERVAL_1DAY,
            limit=30
        )
        if len(bougies) < 7:
            return None

        prix_1mois = float(bougies[0][4])
        variation_1mois = ((prix - prix_1mois) / prix_1mois) * 100

        prix_2sem = float(bougies[15][4])
        variation_2sem = ((prix - prix_2sem) / prix_2sem) * 100

        prix_1sem = float(bougies[23][4])
        variation_1sem = ((prix - prix_1sem) / prix_1sem) * 100

        prix_3j = float(bougies[27][4])
        variation_3j = ((prix - prix_3j) / prix_3j) * 100

        prix_max = max(float(b[2]) for b in bougies)
        prix_min = min(float(b[3]) for b in bougies)

        return {
            "symbole": symbole,
            "prix": prix,
            "variation_24h": variation_24h,
            "variation_3j": variation_3j,
            "variation_1sem": variation_1sem,
            "variation_2sem": variation_2sem,
            "variation_1mois": variation_1mois,
            "prix_max": prix_max,
            "prix_min": prix_min,
            "volume": volume
        }
    except:
        return None

def scorer_crypto(donnee):
    prompt = f"""Tu es un modele d'analyse de marche, pas un trader.

Ton role est de donner un score de qualite de setup entre 0 et 10.

Tu recois :
- Symbole : {donnee['symbole']}
- Prix : {donnee['prix']}$
- Variation 24h : {donnee['variation_24h']:+.2f}%
- Variation 3j : {donnee['variation_3j']:+.2f}%
- Variation 1sem : {donnee['variation_1sem']:+.2f}%
- Variation 2sem : {donnee['variation_2sem']:+.2f}%
- Variation 1mois : {donnee['variation_1mois']:+.2f}%
- Volume : {donnee['volume']:.0f}$

Tu dois :
1. Evaluer si le setup est propre (structure, pas deja trop etendu)
2. Eviter les actifs en pump ou trop volatils
3. Favoriser les configurations stables et repetables
4. Donner un score entre 0 et 10
5. Justifier brievement (1 phrase max)

Important :
- Tu ne dois JAMAIS dire "acheter" ou "vendre"
- Tu ne prends AUCUNE decision finale
- Tu fais uniquement de l'evaluation

Format JSON obligatoire :
{{"score": X, "reason": "..."}}"""

    try:
        reponse = client_openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )
        texte = reponse.choices[0].message.content.strip()
        texte = texte.replace("```json", "").replace("```", "").strip()
        return json.loads(texte)
    except:
        return {"score": 0, "reason": "erreur parsing"}

def acheter(symbole):
    if symbole in CRYPTOS_BLOQUEES:
        print(f"{symbole} bloque - ignore")
        return

    if len(positions_ouvertes) >= MAX_POSITIONS:
        print(f"Max {MAX_POSITIONS} positions atteint - pas d'achat")
        return

    if symbole in positions_ouvertes:
        print(f"Deja en position sur {symbole}")
        return

    try:
        prix = get_prix(symbole)
        info = client_binance.get_symbol_info(symbole)
        step = float([f for f in info['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])
        precision = len(str(step).rstrip('0').split('.')[-1]) if '.' in str(step) else 0
        quantite = round(BUDGET_PAR_POSITION / prix, precision)

        client_binance.order_market_buy(symbol=symbole, quantity=quantite)

        positions_ouvertes[symbole] = {
            "prix_achat": prix,
            "quantite": quantite,
            "stop_loss": round(prix * STOP_LOSS_PCT, 8),
            "take_profit": round(prix * TAKE_PROFIT_PCT, 8),
            "prix_max_atteint": prix
        }
        sauvegarder_positions()
        print(f"ACHAT {symbole} : {quantite} a {prix}$")
        print(f"  Stop loss : {positions_ouvertes[symbole]['stop_loss']}$")
        print(f"  Take profit : {positions_ouvertes[symbole]['take_profit']}$")

    except Exception as e:
        if "not permitted" in str(e) or "-2010" in str(e) or "-2015" in str(e):
            print(f"{symbole} non disponible - ajoute a la liste noire")
            CRYPTOS_BLOQUEES.add(symbole)
            sauvegarder_bloquees()
        else:
            print(f"Erreur achat {symbole} : {e}")

def vendre(symbole, raison="Manuel"):
    if symbole not in positions_ouvertes:
        return
    try:
        quantite = positions_ouvertes[symbole]["quantite"]
        client_binance.order_market_sell(symbol=symbole, quantity=quantite)
        prix_actuel = get_prix(symbole)
        prix_achat = positions_ouvertes[symbole]["prix_achat"]
        profit = (prix_actuel - prix_achat) / prix_achat * 100
        print(f"VENTE {symbole} ({raison}) : {profit:+.2f}%")
        del positions_ouvertes[symbole]
        sauvegarder_positions()
    except Exception as e:
        print(f"Erreur vente {symbole} : {e}")

def gerer_positions():
    for symbole in list(positions_ouvertes.keys()):
        try:
            prix = get_prix(symbole)
            pos = positions_ouvertes[symbole]

            if prix > pos["prix_max_atteint"]:
                positions_ouvertes[symbole]["prix_max_atteint"] = prix
                nouveau_stop = round(prix * TRAILING_STOP_PCT, 8)
                if nouveau_stop > pos["stop_loss"]:
                    positions_ouvertes[symbole]["stop_loss"] = nouveau_stop
                    print(f"Trailing stop {symbole} : {nouveau_stop}$")
                sauvegarder_positions()

            if prix <= pos["stop_loss"]:
                vendre(symbole, "STOP LOSS")
            elif prix >= pos["take_profit"]:
                vendre(symbole, "TAKE PROFIT")

        except Exception as e:
            print(f"Erreur gestion {symbole} : {e}")

def afficher_positions():
    if not positions_ouvertes:
        print("Aucune position ouverte")
        return
    print(f"\nPositions ouvertes ({len(positions_ouvertes)}/{MAX_POSITIONS}) :")
    for symbole, pos in positions_ouvertes.items():
        try:
            prix = get_prix(symbole)
            profit = (prix - pos["prix_achat"]) / pos["prix_achat"] * 100
            print(f"  {symbole} : {profit:+.2f}% | SL:{pos['stop_loss']}$ | TP:{pos['take_profit']}$")
        except:
            pass

def analyser_marche():
    maintenant = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    print(f"\n{'='*50}")
    print(f"Analyse a {maintenant}")
    print(f"{'='*50}")

    gerer_positions()
    afficher_positions()

    if len(positions_ouvertes) >= MAX_POSITIONS:
        print(f"\nMax positions atteint - pas de nouveau scan")
        print("Prochaine analyse dans 15 minutes...")
        return

    symboles = scanner_opportunites()
    symboles = [s for s in symboles if s not in positions_ouvertes]
    print(f"\nOpportunites detectees : {symboles}")

    if not symboles:
        print("Aucune opportunite trouvee")
        print("Prochaine analyse dans 15 minutes...")
        return

    meilleur_score = 0
    meilleur_symbole = None
    meilleure_raison = ""

    for s in symboles:
        d = get_donnees(s)
        if d:
            print(f"{d['symbole']} : {d['prix']:.4f}$ ({d['variation_24h']:+.2f}%)")
            resultat = scorer_crypto(d)
            score = resultat.get("score", 0)
            raison = resultat.get("reason", "")
            print(f"  Score : {score}/10 | {raison}")
            if score > meilleur_score:
                meilleur_score = score
                meilleur_symbole = s
                meilleure_raison = raison

    if meilleur_symbole and meilleur_score >= 5:
        print(f"\nMeilleur setup : {meilleur_symbole} ({meilleur_score}/10) | {meilleure_raison}")
        acheter(meilleur_symbole)
    else:
        print(f"\nAucun setup suffisant (meilleur score : {meilleur_score}/10) - ATTEND")

    print("\nProchaine analyse dans 15 minutes...")

charger_positions()
while True:
    analyser_marche()
    time.sleep(900)
