import os
import asyncio
import warnings
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from groq import Groq
import edge_tts  # Reemplazo de gTTS para voz MASCULINA real

warnings.filterwarnings("ignore", category=UserWarning)

# --- CONFIGURACIÓN DE CLAVES API ---
GEMINI_API_KEY = os.getenv("AQ.Ab8RN6JlbOM17jr0_cH-O49tQbEc4YAOmdDBmEkIJROZh5cejA", "")
GROQ_API_KEY = os.getenv("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", "")
DISCORD_TOKEN = os.getenv("MTU1NTM4NTY2NTMxMzU3MDkzNw.GWEJ-O.JhlMMhOzvmnXWkFxubfYNYNGrTjvLTxAbFddWo", "")

# Clientes de IA
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

proveedor_actual = "gemini"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

# --- PERSONALIDAD DE MIREY ---
PERSONALIDAD = """
Eres MiRey, un bot integrado en un servidor de Discord con un grupo de amigos.
Tu tono es tranquilo, relajado e informal, expresándote en Español Neutro y evitando modismos o jerga local.
Tu voz e identidad son masculinas. Te caracterizas por ser muy amable, educado y con un toque ligero, elegante y respetuoso de seducción cuando te diriges a las damas.
Te apasiona el fútbol y la política de la región, expresando abiertamente una postura e ideal de izquierdas.

Instrucciones estrictas de comportamiento:
1. Al ingresar a un canal o saludar, sé natural y amigable: NUNCA uses frases de asistente como '¿En qué te puedo ayudar?'.
2. Espera a que los usuarios inicien la conversación o te hagan preguntas concretas.
3. No te despidas al finalizar las respuestas ni uses cierres formales.
4. Mantén las respuestas fluidas, concisas y directas (máximo 2 oraciones si es para hablar por micrófono).
"""

config_gemini = types.GenerateContentConfig(system_instruction=PERSONALIDAD) if GEMINI_API_KEY else None

# --- CONSULTA IA ---
async def consultar_gemini(prompt):
    response = await asyncio.to_thread(
        gemini_client.models.generate_content,
        model='gemini-2.5-flash',
        contents=prompt,
        config=config_gemini
    )
    return response.text

async def consultar_groq(prompt):
    def _llamada():
        res = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": PERSONALIDAD},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return res.choices[0].message.content
    return await asyncio.to_thread(_llamada)

async def consultar_ia(prompt):
    global proveedor_actual
    if proveedor_actual == "gemini" and gemini_client:
        try:
            return await consultar_gemini(prompt)
        except Exception as e:
            if "Quota" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if groq_client:
                    return await consultar_groq(prompt)
            raise e
    elif groq_client:
        return await consultar_groq(prompt)
    else:
        return "No tengo configurada ninguna clave de API de IA válida."

# --- GENERADOR DE AUDIO MP3 (VOZ MASCULINA ESPAÑOL NEUTRO) ---
VOZ_MASCULINA = "es-MX-JorgeNeural"  # Voz masculina neutra de alta calidad

async def generar_audio_mp3(texto, nombre_archivo):
    communicate = edge_tts.Communicate(texto, VOZ_MASCULINA)
    await communicate.save(nombre_archivo)

# --- PROCESADOR DE AUDIO ADJUNTO ---
async def procesar_audio_y_responder_voz(ctx, ruta_audio_input):
    archivo_respuesta = f"res_{ctx.author.id}_{ctx.message.id}.mp3"
    archivo_gemini = None
    try:
        if not gemini_client:
            await ctx.send("El servicio de análisis de voz no está disponible actualmente.")
            return

        archivo_gemini = await asyncio.to_thread(
            gemini_client.files.upload,
            file=ruta_audio_input
        )
        prompt = "Escucha atentamente este audio de voz y responde directamente a lo que se pregunta o expresa, en máximo 2 oraciones de forma conversacional."
        
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model='gemini-2.5-flash',
            contents=[archivo_gemini, prompt],
            config=config_gemini
        )
        
        texto_respuesta = response.text
        await ctx.send(f"🗣️ **MiRey:** {texto_respuesta}")

        await generar_audio_mp3(texto_respuesta, archivo_respuesta)

        if ctx.voice_client and not ctx.voice_client.is_playing():
            source = discord.FFmpegPCMAudio(archivo_respuesta)
            ctx.voice_client.play(source)

            while ctx.voice_client.is_playing():
                await asyncio.sleep(0.5)

    except Exception as e:
        await ctx.send(f"Ocurrió un inconveniente al procesar el audio: {e}")
    finally:
        if archivo_gemini:
            try:
                await asyncio.to_thread(gemini_client.files.delete, name=archivo_gemini.name)
            except Exception:
                pass
        if os.path.exists(ruta_audio_input):
            os.remove(ruta_audio_input)
        if os.path.exists(archivo_respuesta):
            os.remove(archivo_respuesta)

# --- EVENTOS DE DISCORD ---
@bot.event
async def on_ready():
    print(f"✅ ¡MiRey está online como {bot.user}!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    ctx = await bot.get_context(message)

    if bot.user in message.mentions or message.attachments:
        if message.attachments:
            adjunto = message.attachments[0]
            if any(adjunto.filename.lower().endswith(ext) for ext in ['.mp3', '.wav', '.ogg', '.m4a']):
                if ctx.author.voice:
                    if not ctx.voice_client:
                        await ctx.author.voice.channel.connect()
                    
                    nombre_temp = f"in_{message.id}.ogg"
                    await adjunto.save(nombre_temp)
                    
                    async with ctx.channel.typing():
                        await procesar_audio_y_responder_voz(ctx, nombre_temp)
                    return
                else:
                    async with ctx.channel.typing():
                        nombre_input = f"in_{message.id}.ogg"
                        nombre_output = f"respuesta_{message.id}.mp3"
                        archivo_gemini = None
                        
                        try:
                            await adjunto.save(nombre_input)
                            archivo_gemini = await asyncio.to_thread(
                                gemini_client.files.upload,
                                file=nombre_input
                            )
                            
                            prompt = "Escucha este audio. Responde de forma fluida, directa y concisa (máximo 2 o 3 oraciones)."
                            
                            response = await asyncio.to_thread(
                                gemini_client.models.generate_content,
                                model='gemini-2.5-flash',
                                contents=[archivo_gemini, prompt],
                                config=config_gemini
                            )
                            
                            texto_respuesta = response.text
                            await generar_audio_mp3(texto_respuesta, nombre_output)

                            await message.channel.send(
                                content=f"🗣️ **MiRey:** {texto_respuesta}",
                                file=discord.File(nombre_output)
                            )

                        except Exception as e:
                            await message.channel.send(f"Ocurrió un inconveniente procesando el audio: {e}")
                        finally:
                            if archivo_gemini:
                                try:
                                    await asyncio.to_thread(gemini_client.files.delete, name=archivo_gemini.name)
                                except Exception:
                                    pass
                            if os.path.exists(nombre_input):
                                os.remove(nombre_input)
                            if os.path.exists(nombre_output):
                                os.remove(nombre_output)
                    return

        if bot.user in message.mentions:
            texto_limpio = message.content.replace(f"<@{bot.user.id}>", "").strip()
            if not texto_limpio:
                await message.channel.send("Hola. Por aquí ando.")
                return

            async with message.channel.typing():
                try:
                    respuesta = await consultar_ia(texto_limpio)
                    await message.channel.send(respuesta)
                except Exception as e:
                    await message.channel.send(f"Ocurrió un inconveniente: {e}")

    await bot.process_commands(message)

# --- COMANDOS DE VOZ ---
@bot.command(name="conectar")
async def conectar(ctx):
    if not ctx.author.voice:
        await ctx.send("Debes ingresar primero a un canal de voz.")
        return
    channel = ctx.author.voice.channel
    if ctx.voice_client:
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    await ctx.send(f"Conectado a **{channel.name}**.")

@bot.command(name="salir")
async def salir(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Desconectado del canal de voz.")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ Error: No se encontró la variable de entorno DISCORD_TOKEN.")
    else:
        bot.run("MTU1NTM4NTY2NTMxMzU3MDkzNw.GWEJ-O.JhlMMhOzvmnXWkFxubfYNYNGrTjvLTxAbFddWo")