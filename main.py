import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
from flask import Flask
from threading import Thread

# ==========================================
# SERWER WWW (WYMAGANY PRZEZ RENDER)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Grajek działa!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# KONFIGURACJA BOTA
# ==========================================
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="/", intents=intents)
queues = {}

# Agresywne opcje wyszukiwania i omijania blokad sieciowych
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'source_address': '0.0.0.0'
}

# Wymuszenie stabilnego strumieniowania i ignorowanie pustych pakietów z hostingu
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 32 -analyzeduration 0',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

@bot.event
async def on_ready():
    print(f'Bot uruchomiony: {bot.user.name}')
    
    # Awatar
    if os.path.exists("avatar.gif"):
        try:
            with open("avatar.gif", "rb") as f:
                await bot.user.edit(avatar=f.read())
            print("Awatar zaktualizowany.")
        except:
            pass
            
    try:
        await bot.tree.sync()
        print("Komendy zsynchronizowane.")
    except Exception as e:
        print(f"Błąd sync: {e}")

async def play_next(interaction, guild_id):
    voice_client = interaction.guild.voice_client
    if voice_client and guild_id in queues and len(queues[guild_id]) > 0:
        next_url, next_title = queues[guild_id].pop(0)
        try:
            source = discord.FFmpegPCMAudio(next_url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(interaction, guild_id)))
            await interaction.channel.send(f"🎶 Gram kolejny utwór: **{next_title}**")
        except:
            bot.loop.create_task(play_next(interaction, guild_id))

@bot.tree.command(name="play", description="Wpisz nazwę piosenki, a bot ją puści")
@app_commands.describe(piosenka="Wpisz tytuł i wykonawcę")
async def play(interaction: discord.Interaction, piosenka: str):
    # Wysłanie natychmiastowej odpowiedzi, żeby Discord nie zerwał połączenia
    await interaction.response.defer()

    if not interaction.user.voice:
        await interaction.followup.send("❌ Wejdź najpierw na kanał głosowy!")
        return

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    # Wymuszenie połączenia i resetowanie zamrożonych sesji głosowych bota
    if not voice_client:
        try:
            voice_client = await voice_channel.connect(timeout=10.0, reconnect=True)
        except Exception as e:
            await interaction.followup.send("❌ Serwer Render blokuje porty głosowe. Zrestartuj bota w panelu Render.")
            return
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    guild_id = interaction.guild_id
    if guild_id not in queues:
        queues[guild_id] = []

    # Wyszukiwanie wyłącznie po tekście (szybkie odpytanie)
    query = f"ytsearch:{piosenka}"
    
    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    except Exception as e:
        await interaction.followup.send("❌ Problem z pobraniem utworu. Spróbuj wpisać inną nazwę.")
        return

    if not data or 'entries' not in data or not data['entries']:
        await interaction.followup.send("❌ Nie znaleziono piosenki o takiej nazwie.")
        return

    track = data['entries'][0]
    if not track:
        await interaction.followup.send("❌ Błąd przetwarzania utworu.")
        return

    url = track['url']
    title = track['title']

    # Odtwarzanie dźwięku
    if not voice_client.is_playing() and not voice_client.is_paused():
        try:
            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(interaction, guild_id)))
            await interaction.followup.send(f"▶️ Muzyka ruszyła! Gram: **{title}**")
        except Exception as e:
            await interaction.followup.send("❌ Odtwarzacz serwera się zawiesił. Spróbuj ponownie za chwilę.")
    else:
        queues[guild_id].append((url, title))
        await interaction.followup.send(f"📁 Dodano do kolejki: **{title}**")

if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Brak TOKENU!")
