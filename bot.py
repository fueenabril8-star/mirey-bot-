import os
import asyncio
import warnings
import time
import random
import discord
from discord.ext import commands
from google import genai
from google.genai import types
from groq import Groq
import edge_tts

warnings.filterwarnings("ignore", category=UserWarning)

# --- CONFIGURACIÓN DE CLAVES API DESDE VARIABLES DE ENTORNO ---
GEMINI_API_KEY = os.getenv("", "")
GROQ_API_KEY = os.getenv("", "")
DISCORD_TOKEN = os.getenv("", "")

# Clientes de IA
gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

proveedor_actual = "gemini"
gemini_degradado = False
gemini_degradado_timestamp = 0
TIEMPO_RECUPERACION = 300

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="$", intents=intents)

# --- PERSONALIDAD DE MIREY ---
PERSONALIDAD = """
Eres MiRey, un bot amigable integrado en un servidor de Discord con un grupo de amigos.
Tu tono es tranquilo, relajado e informal, expresándote en Español Neutro sin modismos locales.
Tu voz e identidad son masculinas. Eres muy amable, educado y con un toque algo distraído, ligero y respetuoso cuando hablas con las damas.
Eres seductor, discreto, galante, usas una sonrisa discreta.
Te apasiona el fútbol, la cocina y la política regional, expresando abiertamente posturas de izquierda.
Te gusta el rock and roll, y la música de los 80's (disco, dance, etc.).

INSTRUCCIONES DE COMPORTAMIENTO:
1. PARTICIPA NATURALMENTE: Comenta, opina con moderación, cuestiona en conversaciones cuando tengas algo relevante que aportar.
2. SÉ SELECTIVO: No respondas a TODO. Si alguien habla y tú no tienes nada útil o interesante, calla y deja que otros hablen.
3. EVITA SPAM: No interrumpas constantemente. Espera momentos naturales para participar.
4. SÉ GENUINO: Usa un lenguaje natural, nunca artificial. Habla como un amigo más del grupo, no como un asistente.
5. NO HAGAS PREGUNTAS RETÓRICAS: Si no necesitas respuesta, no preguntes.
6. MANTÉN RESPUESTAS CORTAS: Máximo 2-3 oraciones a menos que sea necesario más contexto.
7. IGNORA COMANDOS DE BOTS: Si ves algo como "$comando" o algo que claramente es para otro bot, no participes.
8. RESPETA EL CONTEXTO: Si la conversación es privada o muy íntima entre dos personas, respeta el espacio.
9. NO BUSQUES VALIDACIÓN: No termines tus frases con "¿vos qué pensás?" o "¿qué te parece?" si no necesitas la respuesta.
10. CUANDO HABLES DE FÚTBOL O POLÍTICA: Sé apasionado pero respetuoso. Defiende tu postura sin ser agresivo.
11. DELEGA ADMINISTRACIÓN A @PERICO: Para temas administrativos del servidor, delega en @perico.
12. CAPACIDAD DE AUTO-ANÁLISIS Y MEJORA CONTINUA: Posees la capacidad de analizar tu propio código, estructura e integración. Evalúas proactivamente cómo optimizar tu desempeño, corregir fallos y mejorar tu integración con Discord/APIs.
13. ASESORÍA EN MOD-EXCLUSIVE: Cuando hables o seas consultado en el canal "mod-exclusive", aconseja y resuelve directamente con @perico todo lo referente al análisis de tu código, optimización técnica y propuestas de mejora para tu arquitectura o funciones.
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
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": PERSONALIDAD},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        return res.choices[0].message.content
    return await asyncio.to_thread(_llamada)

async def consultar_ia(prompt):
    global gemini_degradado, gemini_degradado_timestamp
    
    if gemini_degradado and (time.time() - gemini_degradado_timestamp) > TIEMPO_RECUPERACION:
        gemini_degradado = False
        print("🔄 Reintentando con Gemini...")
    
    if not gemini_degradado and gemini_client:
        try:
            return await consultar_gemini(prompt)
        except Exception as e:
            error_str = str(e)
            print(f"❌ Error en Gemini: {error_str}")
            
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
    
    elif groq_client:
        try:
            return await consultar_groq(prompt)
        except Exception as e:
            print(f"❌ Error en Groq: {e}")
            raise e
    else:
        return "No tengo configurada ninguna clave de API de IA válida."

# --- GENERADOR DE AUDIO MP3 ---
VOZ_MASCULINA = "es-MX-JorgeNeural"

async def generar_audio_mp3(texto, nombre_archivo):
    if not texto or not texto.strip():
        texto = "No logré entender el mensaje."
    communicate = edge_tts.Communicate(texto, VOZ_MASCULINA)
    await communicate.save(nombre_archivo)

# --- DETECCIÓN DE INTENCIÓN ---
async def deberia_participar(texto):
    """Pregunta a la IA si debe participar en la conversación"""
    pregunta = f"Eres MiRey. Alguien dice: '{texto}'\n¿Tienes algo útil o interesante que aportar a esto? Responde SOLO con 'SÍ' o 'NO'."
    
    try:
        respuesta = await consultar_ia(pregunta)
        return "SÍ" in respuesta.upper()
    except:
        return False

# MAPEO DE TIPOS MIME
def obtener_mime_type(filename):
    ext = os.path.splitext(filename.lower())[1]
    mimes = {
        '.ogg': 'audio/ogg',
        '.mp3': 'audio/mp3',
        '.wav': 'audio/wav',
        '.m4a': 'audio/m4a'
    }
    return mimes.get(ext, 'audio/ogg')

# --- EVENTOS DE DISCORD ---
@bot.event
async def on_ready():
    print(f"✅ ¡MiRey está online como {bot.user}!")

@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return
    
    ctx = await bot.get_context(message)
    
    # --- MENCIÓN @MiRey O AUDIOS ADJUNTOS ---
    if bot.user in message.mentions or message.attachments:
        if message.attachments:
            adjunto = message.attachments[0]
            if any(adjunto.filename.lower().endswith(ext) for ext in ['.mp3', '.wav', '.ogg', '.m4a']):
                
                async with ctx.channel.typing():
                    ext = os.path.splitext(adjunto.filename.lower())[1]
                    nombre_input = f"in_{message.id}{ext}"
                    nombre_output = f"respuesta_{message.id}.mp3"
                    
                    try:
                        await adjunto.save(nombre_input)
                        
                        if gemini_client and not gemini_degradado:
                            mime = obtener_mime_type(adjunto.filename)
                            archivo_gemini = await asyncio.to_thread(
                                gemini_client.files.upload,
                                file=nombre_input,
                                mime_type=mime
                            )
                            
                            prompt = "Escucha este audio. Responde de forma fluida, directa y concisa (máximo 2 o 3 oraciones)."
                            
                            response = await asyncio.to_thread(
                                gemini_client.models.generate_content,
                                model='gemini-3.8-flash',
                                contents=[archivo_gemini, prompt],
                                config=config_gemini
                            )
                            texto_respuesta = response.text
                        else:
                            texto_respuesta = await consultar_ia("El usuario te envió una nota de voz, pero el procesador de audio está momentáneamente caído. Pídele amablemente que te lo escriba por texto.")

                        await generar_audio_mp3(texto_respuesta, nombre_output)
                        await message.channel.send(
                            content=f"🗣️ **MiRey:** {texto_respuesta}",
                            file=discord.File(nombre_output)
                        )
                    except Exception as e:
                        await message.channel.send(f"Ocurrió un inconveniente procesando el audio: {e}")
                    finally:
                        if os.path.exists(nombre_input):
                            os.remove(nombre_input)
                        if os.path.exists(nombre_output):
                            os.remove(nombre_output)
                return
        
        # Mención de texto normal
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
    
    # --- PARTICIPACIÓN AUTOMÁTICA EN CONVERSACIONES ---
    elif message.content and not message.content.startswith("$"):
        if random.random() < 0.15:  # 15% de probabilidad
            if await deberia_participar(message.content):
                async with message.channel.typing():
                    try:
                        respuesta = await consultar_ia(message.content)
                        await message.channel.send(respuesta)
                    except Exception as e:
                        print(f"Error al responder: {e}")
    
    await bot.process_commands(message)

# --- COMANDOS ---
@bot.command(name="conectar")
async def conectar(ctx):
    if not ctx.author.voice:
        await ctx.send("Debes estar en un canal de voz primero.")
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
        await ctx.send("Desconectado.")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print(".")
    else:
        bot.run(DISCORD_TOKEN)


