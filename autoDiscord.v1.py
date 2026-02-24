!pip install -U discord.py yfinance pandas nest-asyncio pytz certifi

import discord
from discord.ext import commands, tasks
import yfinance as yf
import pandas as pd
import ssl
import certifi
import warnings
import nest_asyncio
import datetime as dt
from datetime import time
import pytz
import random

# --- CONFIGURATION ---
TOKEN = 'TOKEN'
CHANNEL_ID = 1475252802107474102
HEURE_ALERTE = 8
MINUTE_ALERTE = 0
TIMEZONE = pytz.timezone("Europe/Paris")

SESSION_ID = random.randint(1000, 9999)
dernier_envoi_date = None

nest_asyncio.apply()
warnings.simplefilter(action='ignore', category=FutureWarning)
ssl._create_default_https_context = ssl.create_default_context(cafile=certifi.where())

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# --- LOGIQUE DE CALCUL ---
def get_market_analysis():
    symbol = "NQ=F"
    data_1m = yf.download(symbol, period="5d", interval="1m", progress=False, auto_adjust=True)
    if data_1m.empty: raise ValueError("Données 1m indisponibles.")
    if isinstance(data_1m.columns, pd.MultiIndex): data_1m.columns = data_1m.columns.get_level_values(0)
    if data_1m.index.tz is None: data_1m.index = data_1m.index.tz_localize('UTC')
    data_1m.index = data_1m.index.tz_convert('Europe/Paris')

    df_asia_filter = data_1m[(data_1m.index.hour >= 2) & (data_1m.index.hour < 6)]
    if df_asia_filter.empty: raise ValueError("Session Asia introuvable.")

    last_session_date = df_asia_filter.index.date[-1]
    asia_session = df_asia_filter[df_asia_filter.index.date == last_session_date]
    a_high, a_low = float(asia_session["High"].max()), float(asia_session["Low"].min())
    range_asia = a_high - a_low

    data_h1 = yf.download(symbol, period="10d", interval="60m", progress=False, auto_adjust=True)
    if isinstance(data_h1.columns, pd.MultiIndex): data_h1.columns = data_h1.columns.get_level_values(0)
    tr_h1 = pd.concat([data_h1["High"]-data_h1["Low"], (data_h1["High"]-data_h1["Close"].shift(1)).abs(), (data_h1["Low"]-data_h1["Close"].shift(1)).abs()], axis=1).max(axis=1)
    atr14_h1 = tr_h1.tail(14).mean()

    data_d = yf.download(symbol, period="30d", interval="1d", progress=False, auto_adjust=True)
    if isinstance(data_d.columns, pd.MultiIndex): data_d.columns = data_d.columns.get_level_values(0)
    tr_d = pd.concat([data_d["High"]-data_d["Low"], (data_d["High"]-data_d["Close"].shift(1)).abs(), (data_d["Low"]-data_d["Close"].shift(1)).abs()], axis=1).max(axis=1)
    atr14_daily = tr_d.tail(14).mean()

    ratio_h1 = range_asia / atr14_h1
    ratio_daily = (range_asia / atr14_daily) * 100

    if ratio_h1 < 0.6: status, interp = "🔥 ASIA COMPRESSÉE", "• un sweep : 80/88%\n• sweep les deux : 25/30%\n• aucun sweep : 12/20%"
    elif ratio_h1 < 1.0: status, interp = "✅ ASIA NORMAL", "• un sweep : 65/75%\n• sweep les deux : 18/24%\n• aucun sweep : 25/35%"
    elif ratio_h1 < 1.4: status, interp = "⚠️ ASIA ÉTENDUE", "• un sweep : 50/60%\n• sweep les deux : 12/18%\n• aucun sweep : 40/50%"
    else: status, interp = "❄️ ASIA EXPANSION", "• un sweep : 40/50%\n• sweep les deux : 8/12%\n• aucun sweep : 50/60%"

    if ratio_daily < 22: d_status, d_stats = "🚀 HAUTE PROBA EXPANSION", "• Sortie franche : 85%\n• Trend Day : 70%"
    elif ratio_daily < 33: d_status, d_stats = "⚖️ JOURNÉE ÉQUILIBRÉE", "• Sortie + tendance : 60%\n• Risque Fakeout : 30/40%"
    else: d_status, d_stats = "🐢 ASIA LARGE", "• Expansion limitée : 35/45%\n• Marché Choppy : 60%"

    return {
        "date": last_session_date, "high": a_high, "low": a_low, "range": range_asia,
        "ratio_h1": ratio_h1, "ratio_daily": ratio_daily,
        "status": status, "interp": interp, "d_status": d_status, "d_stats": d_stats
    }

# --- BOUCLE UNIQUE DISCRÈTE ---
@tasks.loop(seconds=30)
async def report_loop():
    global dernier_envoi_date
    now = dt.datetime.now(TIMEZONE)

    # On ne print plus rien ici pour garder la console propre

    if now.hour == HEURE_ALERTE and now.minute == MINUTE_ALERTE:
        if dernier_envoi_date != now.date():
            dernier_envoi_date = now.date()

            if now.weekday() < 5:
                channel = bot.get_channel(CHANNEL_ID)
                if channel:
                    try:
                        res = get_market_analysis()
                        embed = discord.Embed(
                            title=f"📊 Analyse NQ - {res['date']}",
                            description="Extraction session 02h00 - 06h00 (Paris)",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="📏 Range Asia", value=f"High: `{res['high']:.2f}`\nLow: `{res['low']:.2f}`\n**Total: {res['range']:.2f} pts**", inline=False)
                        embed.add_field(name="📈 Ratios", value=f"Ratio H1: `{res['ratio_h1']:.2f}`\n% ATR Daily: `{res['ratio_daily']:.2f}%`", inline=False)
                        embed.add_field(name=f"📌 SWEEPS : {res['status']}", value=res['interp'], inline=False)
                        embed.add_field(name=f"📌 TENDANCE : {res['d_status']}", value=res['d_stats'], inline=False)
                        embed.set_footer(text=f"ID: {SESSION_ID} | {now.strftime('%H:%M')}")

                        await channel.send("🔔 **RAPPORT QUOTIDIEN NASDAQ**", embed=embed)
                        print(f"✅ Rapport envoyé avec succès à {now.strftime('%H:%M:%S')}")
                    except Exception as e:
                        print(f"❌ Erreur lors de l'envoi auto : {e}")
                        dernier_envoi_date = None

@bot.event
async def on_ready():
    print(f'--- BOT ACTIF (ID: {SESSION_ID}) ---')
    print(f'Prêt pour l\'envoi quotidien à {HEURE_ALERTE:02d}:{MINUTE_ALERTE:02d}')
    if not report_loop.is_running():
        report_loop.start()

@bot.command(name='analyse')
async def analyse(ctx):
    try:
        # On récupère les mêmes données que pour l'envoi auto
        res = get_market_analysis()
        now = dt.datetime.now(TIMEZONE)
        
        # On crée un Embed identique au rapport quotidien
        embed = discord.Embed(
            title=f"📊 Analyse Manuelle NQ - {res['date']}",
            description="Extraction session 02h00 - 06h00 (Paris)",
            color=discord.Color.green() # Couleur verte pour différencier du rapport auto
        )
        
        # On ajoute TOUS les champs manquants
        embed.add_field(
            name="📏 Range Asia", 
            value=f"High: `{res['high']:.2f}`\nLow: `{res['low']:.2f}`\n**Total: {res['range']:.2f} pts**", 
            inline=False
        )
        
        embed.add_field(
            name="📈 Ratios", 
            value=f"Ratio H1: `{res['ratio_h1']:.2f}`\n% ATR Daily: `{res['ratio_daily']:.2f}%`", 
            inline=False
        )
        
        embed.add_field(
            name=f"📌 SWEEPS : {res['status']}", 
            value=res['interp'], 
            inline=False
        )
        
        embed.add_field(
            name=f"📌 TENDANCE : {res['d_status']}", 
            value=res['d_stats'], 
            inline=False
        )
        
        embed.set_footer(text=f"Manuel | ID: {SESSION_ID} | {now.strftime('%H:%M')}")

        await ctx.send("🔍 **ANALYSE MANUELLE DU NASDAQ**", embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Erreur lors de l'analyse : {e}")

bot.run(TOKEN)