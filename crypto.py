from binance.client import Client
import openai
import time
import json
from datetime import datetime

CLE_API_BINANCE = os.environ.get("CLE_API_BINANCE")
CLE_SECRETE_BINANCE = os.environ.get("CLE_SECRETE_BINANCE")
CLE_OPENAI = os.environ.get("CLE_OPENAI")
client_binance = Client(CLE_API_BINANCE, CLE_SECRETE_BINANCE)
openai.api_key = CLE_OPENAI

# Gestion du risque
BUDGET_PAR_POSITION = 10
STOP_LOSS_PCT = 0.95       # -5%
TAKE_PROFIT_PCT = 1.10     # +10%
TRAILING_STOP_PCT = 0.97   # suit le prix a -3%
MAX_POSITIONS = 3
CRYPTOS_BLOQUEES = set()

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
        if t['symbol'].endswith('USDT')
        and float(t['quoteVolume']) > 500000
        and float(t['priceChangePercent']) > 0
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
            limit=14
        )
        if len(bougies) < 7:
            return None

        prix_2sem = float(bougies[0][4])
        variation_2sem = ((prix - prix_2sem) / prix_2sem) * 100
        prix_max = max(float(b[2]) for b in bougies)
        prix_min = min(float(b[3]) for b in bougies)

        return {
            "symbole": symbole,
            "prix": prix,
            "variation_24h": variation_24h,
            "variation_2sem": variation_2sem,
            "prix_max": prix_max,
            "prix_min": prix_min,
            "volume": volume
        }
    except:
        return None

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
        print(f"✓ ACHAT {symbole} : {quantite} a {prix}$")
        print(f"  Stop loss : {positions_ouvertes[symbole]['stop_loss']}$")
        print(f"  Take profit : {positions_ouvertes[symbole]['take_profit']}$")

    except Exception as e:
        if "not permitted" in str(e) or "-2010" in str(e):
            print(f"✗ {symbole} non disponible dans ta region - ajoute a la liste noire")
            CRYPTOS_BLOQUEES.add(symbole)
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
        print(f"✓ VENTE {symbole} ({raison}) : {profit:+.2f}%")
        del positions_ouvertes[symbole]
        sauvegarder_positions()
    except Exception as e:
        print(f"Erreur vente {symbole} : {e}")

def gerer_positions():
    for symbole in list(positions_ouvertes.keys()):
        try:
            prix = get_prix(symbole)
            pos = positions_ouvertes[symbole]

            # Trailing stop loss
            if prix > pos["prix_max_atteint"]:
                positions_ouvertes[symbole]["prix_max_atteint"] = prix
                nouveau_stop = round(prix * TRAILING_STOP_PCT, 8)
                if nouveau_stop > pos["stop_loss"]:
                    positions_ouvertes[symbole]["stop_loss"] = nouveau_stop
                    print(f"Trailing stop {symbole} mis a jour : {nouveau_stop}$")
                sauvegarder_positions()

            # Stop loss
            if prix <= pos["stop_loss"]:
                vendre(symbole, "STOP LOSS")

            # Take profit
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
        print(f"\nMax positions atteint ({MAX_POSITIONS}) - pas de nouveau scan")
        print("Prochaine analyse dans 30 minutes...")
        return

    symboles = scanner_opportunites()
    symboles = [s for s in symboles if s not in positions_ouvertes]
    print(f"\nOpportunites detectees : {symboles}")

    donnees_texte = []
    for s in symboles:
        d = get_donnees(s)
        if d:
            donnees_texte.append(
                f"{d['symbole']} : Prix={d['prix']:.4f}$ | 24h={d['variation_24h']:+.2f}% | 2sem={d['variation_2sem']:+.2f}% | Vol={d['volume']:.0f}$"
            )
            print(f"{d['symbole']} : {d['prix']:.4f}$ ({d['variation_24h']:+.2f}%)")

    if not donnees_texte:
        print("Pas de donnees disponibles")
        return

    reponse = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "user", "content": f"""Tu es un trader crypto expert avec une gestion du risque stricte.

Cryptos disponibles :
{chr(10).join(donnees_texte)}

Positions ouvertes : {list(positions_ouvertes.keys()) if positions_ouvertes else 'Aucune'}
Places disponibles : {MAX_POSITIONS - len(positions_ouvertes)}/{MAX_POSITIONS}

Choisis UNE seule crypto a acheter si opportunite reelle, sinon ATTEND.
Reponds sous ce format :
SYMBOLE : ACHETE ou ATTEND | Confiance X/10 | raison courte"""}
        ]
    )

    resultat = reponse.choices[0].message.content.strip()
    print(f"\nDecision IA : {resultat}")

    for symbole in symboles:
        if symbole in resultat and "ACHETE" in resultat.split(symbole)[1].split('\n')[0]:
            acheter(symbole)
            break

    print("\nProchaine analyse dans 30 minutes...")

charger_positions()
while True:
    analyser_marche()
    time.sleep(1800)