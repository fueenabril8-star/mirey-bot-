import os
import asyncio
import warnings
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from groq import Groq
import edge_tts  # Reemplazo de gTTS para voz MASCULINA real
import time

warnings.filterwarnings("ignore", category=UserWarning)

# --- CONFIGURACIÓN DE CLAVES API ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Clientes de IA
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

proveedor_actual = "gemini"
gemini_degradado = False  # Flag para trackear si Gemini está degradado
gemini_degradado_timestamp = 0
TIEMPO_RECUPERACION = 300  # 5 minutos antes de reintentar Gemini

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
5. Participa en conversaciones naturales: comenta, opina, cuestiona cuando sea relevante.
6. Si no tienes algo útil o interesante que decir en una conversación, no respondas.
"""

config_gemini = types.GenerateContentConfig(system_instruction=PERSONALIDAD) if GEMINI_API_KEY else None

# --- CONSULTA IA ---
async def consultar_gemini(prompt):
    response = await asyncio.to_thread(
        gemini_client.models.generate_content,
        model='gemini-3.8-flash',
        contents=prompt,
        config=config_gemini
    )
    return response.text

async def consultar_groq(prompt):
    def _llamada():
        res = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {"role": "system", "content": PERSONALIDAD},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return res.choices[0].message.content
    return await asyncio.to_thread(_llamada)

async def consultar_ia(prompt):
    global proveedor_actual, gemini_degradado, gemini_degradado_timestamp
    
    # Verificar si es hora de reintentar Gemini
    if gemini_degradado and (time.time() - gemini_degradado_timestamp) > TIEMPO_RECUPERACION:
        gemini_degradado = False
        print("🔄 Reintentando con Gemini...")
    
    # Intentar con Gemini primero si está disponible
    if not gemini_degradado and gemini_client:
        try:
            return await consultar_gemini(prompt)
        except Exception as e:
            error_str = str(e)
            print(f"❌ Error en Gemini: {error_str}")
            
            # Detectar errores de lag/unavailability
            if any(keyword in error_str for keyword in ["503", "UNAVAILABLE", "high demand", "Quota", "RESOURCE_EXHAUSTED"]):
                print("⚠️ Gemini está saturado. Cambiando a Groq...")
                gemini_degradado = True
                gemini_degradado_timestamp = time.time()
                
                if groq_client:
                    try:
                        return await consultar_groq(prompt)
                    except Exception as groq_error:
                        raise Exception(f"Groq fallback también falló: {groq_error}")
            raise e
    
    # Usar Groq si Gemini está degradado
    elif gemini_degradado and groq_client:
        try:
            return await consultar_groq(prompt)
        except Exception as e:
            print(f"❌ Error en Groq: {e}")
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
async def procesar_audio_y_responder(message, ruta_audio_input):
    """Procesa audios y responde con mensaje de audio en el chat de texto"""
    archivo_respuesta = f"res_{message.author.id}_{message.id}.mp3"
    archivo_gemini = None
    
    try:
        if not gemini_client:
            await message.channel.send("El servicio de análisis de voz no está disponible actualmente.")
            return

        async with message.channel.typing():
            # 1. Guardar el archivo localmente
            # 2. Subir el audio a Gemini
            archivo_gemini = await asyncio.to_thread(
                gemini_client.files.upload,
                file=ruta_audio_input
            )
            
            prompt = "Escucha este audio. Responde de forma fluida, directa y concisa (máximo 2 o 3 oraciones)."
            
            response = await asyncio.to_thread(
                gemini_client.models.generate_content,
                model='gemini-3.8-flash',
                contents=[archivo_gemini, prompt],
                config=config_gemini
            )
            
            texto_respuesta = response.text
            # 3. Convertir la respuesta a audio MP3
            await generar_audio_mp3(texto_respuesta, archivo_respuesta)
            # 4. Responder en la sala de texto con el archivo de audio
            await message.channel.send(
                content=f"🗣️ **MiRey:** {texto_respuesta}",
                file=discord.File(archivo_respuesta)
            )

    except Exception as e:
        await message.channel.send(f"Ocurrió un inconveniente procesando el audio: {e}")
    finally:
        # Limpiar archivos temporales
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
    # Ignorar mensajes propios
    if message.author == bot.user:
        return
    
    ctx = await bot.get_context(message)
    
    # --- MENCIÓN @MiRey: Procesa audios y responde con un mensaje de audio en el chat de texto ---
    if bot.user in message.mentions or message.attachments:
        # Verificar si envió un archivo de audio / nota de voz
        if message.attachments:
            adjunto = message.attachments[0]
            if any(adjunto.filename.lower().endswith(ext) for ext in ['.mp3', '.wav', '.ogg', '.m4a']):
                nombre_input = f"in_{message.id}.ogg"
                await adjunto.save(nombre_input)
                await procesar_audio_y_responder(message, nombre_input)
                return
        
        # Si es solo una consulta de texto normal mencionándolo
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
            return
    
    # --- PARTICIPACIÓN AUTOMÁTICA EN CONVERSACIONES (SIN MENCIÓN) ---
    # El bot participa en conversaciones naturales cuando cree que tiene algo útil que decir
    if message.content and not message.author.bot and not message.content.startswith("$"):
        # Opcionalmente, agregar lógica para detectar si es pregunta o comentario dirigido al bot
        # Por ahora, solo participa si se menciona
        pass
    
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
        bot.run(DISCORD_TOKEN)

