import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
from flask import Flask
from threading import Thread

# ==========================================
# 1. SERWER WWW DLA RENDERA (KEEP ALIVE)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot działa, śpiewa i nie śpi!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# 2. KONFIGURACJA BOTA DISCORD
# ==========================================
intents = discord.Intents.default()
intents.message_content = True 

bot = commands.Bot(command_prefix="/", intents=intents)

queues = {}

# Konfiguracja yt-dlp obsługująca YT oraz SoundCloud
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

@bot.event
async def on_ready():
    print(f'Zalogowano jako: {bot.user.name}')
    
    # Obsługa animowanego awatara z pliku avatar.gif
    if os.path.exists("avatar.gif"):
        try:
            with open("avatar.gif", "rb") as f:
                avatar_bytes = f.read()
            await bot.user.edit(avatar=avatar_bytes)
            print("Pomyślnie zaktualizowano animowany awatar bota!")
        except discord.HTTPException as e:
            print(f"Discord zablokował zmianę awataru (ratelimit): {e}")
        except Exception as e:
            print(f"Nie udało się zmienić awataru: {e}")
            
    try:
        synced = await bot.tree.sync()
        print(f"Zsynchronizowano {len(synced)} komend typu Slash.")
    except Exception as e:
        print(f"Błąd synchronizacji komend: {e}")

async def play_next(interaction, guild_id):
    voice_client = interaction.guild.voice_client
    if voice_client and guild_id in queues and len(queues[guild_id]) > 0:
        next_url, next_title = queues[guild_id].pop(0)
        try:
            source = discord.FFmpegPCMAudio(next_url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(interaction, guild_id)))
            await interaction.channel.send(f"🎶 Teraz gram z kolejki: **{next_title}**")
        except Exception as e:
            await interaction.channel.send(f"❌ Błąd podczas odtwarzania kolejnego utworu: {e}")

@bot.tree.command(name="play", description="Puszcza muzykę z YT/linku lub wyszukuje po nazwie")
@app_commands.describe(utwor="Wklej link (np. z YT) lub wpisz tytuł piosenki")
async def play(interaction: discord.Interaction, utwor: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        await interaction.followup.send("❌ Musisz najpierw wejść na kanał głosowy!")
        return

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    if not voice_client:
        voice_client = await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    guild_id = interaction.guild_id
    if guild_id not in queues:
        queues[guild_id] = []

    query = utwor
    
    # SYSTEM WYKRYWANIA:
    # Jeśli to NIE jest link (nie zaczyna się od http), szukaj tekstu na SoundCloud (bezpieczne, nie zacina serwera)
    if not query.startswith("http://") and not query.startswith("https://"):
        query = f"scsearch:{query}"
    
    # Jeśli to JEST link, yt-dlp obsłuży go bezpośrednio (np. link do YouTube, SoundCloud, itp.)

    loop = asyncio.get_event_loop()
    try:
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    except Exception as e:
        await interaction.followup.send(f"❌ Nie udało się pobrać utworu (Błąd: {e}).")
        return

    # Wyciąganie pierwszego wyniku, jeśli to było wyszukiwanie tekstowe
    if 'entries' in data:
        if not data['entries']:
            await interaction.followup.send("❌ Nie znaleziono żadnego pasującego utworu.")
            return
        data = data['entries'][0]

    url = data['url']
    title = data['title']

    try:
        if not voice_client.is_playing() and not voice_client.is_paused():
            source = discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: bot.loop.create_task(play_next(interaction, guild_id)))
            await interaction.followup.send(f"▶️ Teraz gram: **{title}**")
        else:
            queues[guild_id].append((url, title))
            await interaction.followup.send(f"📁 Dodano do kolejki: **{title}**")
    except Exception as e:
        await interaction.followup.send(f"❌ Problem z odtwarzaczem audio: {e}")

if __name__ == "__main__":
    keep_alive()
    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("❌ BŁĄD SYSTEMU: Brak zmiennej środowiskowej DISCORD_TOKEN!")
