"""
Simple Cleaner
--------------
App sencilla para encontrar los archivos que más espacio ocupan en tu PC
y decidir cuáles borrar.

Requisitos: Python 3.8+ y customtkinter
    python -m pip install customtkinter

Ejecutar:
    python SimpleCleanerES.py
"""

import itertools
import os
import platform
import queue
import subprocess
import threading
import tkinter as tk
import traceback
from datetime import datetime
from tkinter import font as tkfont
from tkinter import ttk

import customtkinter as ctk

# ---------------------------------------------------------------- Tema
# Paleta oscura con acento rojo (inspirada en el estilo de ExitLag)
FONDO = "#141414"
FONDO_MODAL = "#0C0C0C"
PANEL = "#1B1B1B"
ELEVADO = "#262626"
BORDE = "#343434"
TEXTO = "#F2F2F2"
TEXTO_SUAVE = "#8C8C8C"
ROJO = "#D61515"
ROJO_HOVER = "#EB2A2A"
ROJO_OSCURO = "#8E0F0F"
ROJO_SELECCION = "#3B1515"
ROJO_CLARO = "#FF6B6B"
VERDE = "#4CC38A"

CARPETA_APP = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- Fuentes
# Coolvetica (Typodermic) se carga desde la carpeta del script, sin instalarla.
# Uso personal: no incluyas el .otf si distribuyes la app (ver EULA).
NOMBRE_FUENTE_PROPIA = "Coolvetica"
RUTA_FUENTE_PROPIA = os.path.join(CARPETA_APP, "Coolvetica Rg.otf")

# Para títulos y números: si Coolvetica no carga, se usa la primera de esta lista.
FUENTES_RESPALDO_TITULO = [
    "Varela Round",
    "Nunito",
    "Quicksand",
    "Arial Rounded MT Bold",
]

# Para el resto de textos, se prefieren variantes finas del sistema.
FUENTES_TEXTO_FINAS = [
    "Segoe UI Light",       # Windows
    "Helvetica Neue Light", # macOS
    "Ubuntu Light",         # Linux
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
]

# Escaneo en paralelo: varios hilos recorriendo carpetas a la vez.
N_HILOS = min(32, (os.cpu_count() or 4) * 4)

# Tabla: alto de cada fila, alto aproximado de la cabecera y filas por rueda.
ALTO_FILA = 38
ALTO_CABECERA = 40
PASO_RUEDA = 3

# Espera (ms) tras la última tecla antes de filtrar.
ESPERA_BUSQUEDA_MS = 120

# Segundos de cuenta atrás antes de poder confirmar un borrado.
CUENTA_ATRAS = 5

ES_WINDOWS = platform.system() == "Windows"
ATRIBUTO_REPARSE = 0x400  # Windows: junctions y enlaces especiales

UN_GB = 1024 ** 3

# Quita tildes y diéresis, también las versiones separadas (macOS usa NFD).
TABLA_SIN_TILDES = str.maketrans(
    "áàäâãéèëêíìïîóòöôõúùüûñç",
    "aaaaaeeeeiiiiooooouuuunc",
    "\u0300\u0301\u0302\u0303\u0308",
)

# ---------------------------------------------------------------- Icono
# Logo que se usa como icono de la ventana. Se busca en este orden.
RUTAS_LOGO = [
    os.path.join(CARPETA_APP, "Simple_Cleaner_Logo_NOBG_1.png"),
    os.path.join(CARPETA_APP, "Simple_Cleaner_Logo_NOBG.png"),
]
RUTA_LOGO = next((r for r in RUTAS_LOGO if os.path.isfile(r)), None)
RUTA_ICONO_WINDOWS = os.path.join(CARPETA_APP, "Simple_Cleaner_Logo_NOBG.ico")

# Color de fondo del icono. None = logo tal cual, con fondo transparente.
# Si la barra de título o la de tareas es clara, la S blanca no se verá:
# en ese caso pon un color, por ejemplo "#141414".
COLOR_FONDO_ICONO = None

# Fuentes en negrita para el icono de respaldo (en orden de preferencia).
FUENTES_ICONO = [
    "arialbd.ttf",                                   # Windows
    "Arial Bold.ttf",                                # macOS / Linux
    "DejaVuSans-Bold.ttf",                           # Linux
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _cargar_fuente_icono(tamano):
    from PIL import ImageFont

    for nombre in FUENTES_ICONO:
        try:
            return ImageFont.truetype(nombre, tamano)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tamano)   # Pillow 10.1 o superior
    except TypeError:
        return ImageFont.load_default()


def _quitar_fondo_blanco(imagen):
    """
    Si el PNG no tiene transparencia real (fondo blanco opaco), convierte
    los píxeles casi blancos en transparentes.
    """
    if imagen.getchannel("A").getextrema()[0] != 255:
        return imagen                       # ya tiene transparencia

    pixeles = [
        (r, g, b, 0) if (r > 245 and g > 245 and b > 245) else (r, g, b, a)
        for r, g, b, a in imagen.getdata()
    ]
    imagen.putdata(pixeles)
    return imagen


def _icono_desde_logo(tamano):
    """Usa el logo como icono, ocupando casi todo el cuadrado."""
    from PIL import Image, ImageDraw

    logo = Image.open(RUTA_LOGO).convert("RGBA")
    logo = _quitar_fondo_blanco(logo)

    # Recortar los bordes transparentes para que el logo ocupe todo el espacio
    caja = logo.split()[-1].getbbox()
    if caja:
        logo = logo.crop(caja)

    # Escalar el logo manteniendo proporciones, con un pequeño margen
    lado = tamano * 0.9
    escala = min(lado / logo.width, lado / logo.height)
    tam_logo = (max(1, round(logo.width * escala)), max(1, round(logo.height * escala)))
    logo = logo.resize(tam_logo, Image.LANCZOS)

    img = Image.new("RGBA", (tamano, tamano), (0, 0, 0, 0))
    if COLOR_FONDO_ICONO:
        ImageDraw.Draw(img).rounded_rectangle(
            (0, 0, tamano - 1, tamano - 1),
            radius=int(tamano * 0.22),
            fill=COLOR_FONDO_ICONO,
        )

    x = (tamano - tam_logo[0]) // 2
    y = (tamano - tam_logo[1]) // 2
    img.alpha_composite(logo, (x, y))
    return img


def _icono_dibujado(tamano):
    """Icono de respaldo: fondo oscuro redondeado, una S blanca y una C roja."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (tamano, tamano), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, tamano - 1, tamano - 1),
        radius=int(tamano * 0.22),
        fill=FONDO,
    )

    fuente = _cargar_fuente_icono(int(tamano * 0.82))
    caja_s = draw.textbbox((0, 0), "S", font=fuente)
    caja_c = draw.textbbox((0, 0), "C", font=fuente)
    ancho_s = caja_s[2] - caja_s[0]
    ancho_c = caja_c[2] - caja_c[0]
    alto = max(caja_s[3] - caja_s[1], caja_c[3] - caja_c[1])
    separacion = int(tamano * 0.02)

    # Centrar el conjunto "SC" en el icono
    x = (tamano - (ancho_s + separacion + ancho_c)) // 2
    y = (tamano - alto) // 2

    draw.text((x - caja_s[0], y - caja_s[1]), "S", font=fuente, fill="#FFFFFF")
    x_c = x + ancho_s + separacion
    draw.text((x_c - caja_c[0], y - caja_c[1]), "C", font=fuente, fill=ROJO)
    return img


def crear_icono(tamano=256):
    """Devuelve el icono de la app: el logo si existe, o el dibujado de respaldo."""
    if RUTA_LOGO:
        try:
            return _icono_desde_logo(tamano)
        except Exception:
            traceback.print_exc()
    return _icono_dibujado(tamano)


# ---------------------------------------------------------------- Lógica
def cargar_fuente_propia(ruta):
    """
    Registra un archivo de fuente solo para este programa, sin instalarlo
    en el sistema. Devuelve True si se ha registrado correctamente.
    """
    if not os.path.isfile(ruta):
        return False

    sistema = platform.system()
    try:
        if sistema == "Windows":
            import ctypes
            from ctypes import wintypes

            FR_PRIVATE = 0x10
            gdi32 = ctypes.WinDLL("gdi32")
            agregar = gdi32.AddFontResourceExW
            agregar.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.LPVOID]
            agregar.restype = ctypes.c_int
            return agregar(ruta, FR_PRIVATE, None) > 0

        if sistema == "Darwin":
            import ctypes

            ct = ctypes.CDLL(
                "/System/Library/Frameworks/CoreText.framework/CoreText"
            )
            cf = ctypes.CDLL(
                "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
            )
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool,
            ]
            ruta_bytes = ruta.encode("utf-8")
            url = cf.CFURLCreateFromFileSystemRepresentation(
                None, ruta_bytes, len(ruta_bytes), False
            )
            ct.CTFontManagerRegisterFontsForURL.argtypes = [
                ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
            ]
            ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
            kCTFontManagerScopeProcess = 1
            return bool(ct.CTFontManagerRegisterFontsForURL(
                url, kCTFontManagerScopeProcess, None
            ))

        # Linux: fontconfig
        import ctypes

        fc = ctypes.CDLL("libfontconfig.so.1")
        fc.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        fc.FcConfigAppFontAddFile.restype = ctypes.c_int
        return bool(fc.FcConfigAppFontAddFile(None, ruta.encode("utf-8")))
    except Exception:
        traceback.print_exc()
        return False


def carpetas_a_escanear():
    """Devuelve las carpetas que se van a revisar según el sistema operativo."""
    carpetas = [os.path.expanduser("~")]
    sistema = platform.system()

    if sistema == "Windows":
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            ruta = os.environ.get(variable)
            if ruta and os.path.isdir(ruta):
                carpetas.append(ruta)
    elif sistema == "Darwin":  # macOS
        carpetas.append("/Applications")

    return carpetas


def formatear_tamano(num_bytes):
    """Convierte bytes a un texto legible (GB, MB, KB)."""
    gb = num_bytes / UN_GB
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = num_bytes / (1024 ** 2)
    if mb >= 1:
        return f"{mb:.1f} MB"
    return f"{num_bytes / 1024:.0f} KB"


def formatear_fecha(timestamp):
    try:
        return datetime.fromtimestamp(timestamp).strftime("%d/%m/%Y  %H:%M")
    except (OverflowError, OSError, ValueError):
        return "Desconocido"


def formatear_numero(n):
    """12345 -> '12.345'"""
    return f"{n:,}".replace(",", ".")


def normalizar(texto):
    """Minúsculas y sin tildes, para que 'Música' coincida con 'musica'."""
    return texto.lower().translate(TABLA_SIN_TILDES)


def escanear(carpetas, contadores):
    """
    Recorre las carpetas con varios hilos a la vez y devuelve TODOS los
    archivos encontrados como tuplas (tamaño, ruta, ultimo_uso, nombre).

    `contadores` es una lista (una posición por hilo) con tuplas
    (archivos, carpetas) que se van actualizando para enseñar el progreso.
    """
    cola = queue.Queue()
    for carpeta in carpetas:
        cola.put(carpeta)

    listas = [[] for _ in contadores]

    def trabajador(idx):
        registros = listas[idx]
        archivos = 0
        carpetas_vistas = 0
        while True:
            carpeta = cola.get()
            if carpeta is None:      # señal de fin
                return
            carpetas_vistas += 1
            try:
                with os.scandir(carpeta) as entradas:
                    for e in entradas:
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if ES_WINDOWS:
                                    attrs = getattr(
                                        e.stat(follow_symlinks=False),
                                        "st_file_attributes", 0,
                                    )
                                    if attrs & ATRIBUTO_REPARSE:
                                        continue
                                cola.put(e.path)
                            elif e.is_file(follow_symlinks=False):
                                st = e.stat(follow_symlinks=False)
                                registros.append((
                                    st.st_size,
                                    e.path,
                                    max(st.st_atime, st.st_mtime),
                                    e.name,
                                ))
                                archivos += 1
                                if archivos & 2047 == 0:   # progreso cada 2048
                                    contadores[idx] = (archivos, carpetas_vistas)
                        except OSError:
                            continue
            except OSError:
                pass
            finally:
                contadores[idx] = (archivos, carpetas_vistas)
                cola.task_done()

    hilos = [
        threading.Thread(target=trabajador, args=(i,), daemon=True)
        for i in range(len(contadores))
    ]
    for h in hilos:
        h.start()

    cola.join()                      # espera a que no quede ninguna carpeta
    for _ in hilos:
        cola.put(None)
    for h in hilos:
        h.join()

    return list(itertools.chain.from_iterable(listas))


def abrir_ubicacion(ruta):
    """Abre el explorador de archivos mostrando el archivo seleccionado."""
    try:
        sistema = platform.system()
        if sistema == "Windows":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(ruta)])
        elif sistema == "Darwin":
            subprocess.Popen(["open", "-R", ruta])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(ruta)])
    except Exception:
        pass


class Indice:
    """
    Guarda los archivos en listas paralelas (una lista por dato) en lugar de
    un objeto por archivo: usa mucha menos memoria y ordenar o filtrar es
    más rápido. Cada archivo se identifica por su posición (su id).
    """

    COLUMNAS_ORDENABLES = ("tamano", "nombre", "ultimo_uso")

    def __init__(self, registros):
        self.tamanos = [r[0] for r in registros]
        self.rutas = [r[1] for r in registros]
        self.fechas = [r[2] for r in registros]
        self.nombres_norm = [normalizar(r[3]) for r in registros]
        self.total_bytes = sum(self.tamanos)

        self._claves = {
            "tamano": self.tamanos,
            "nombre": self.nombres_norm,
            "ultimo_uso": self.fechas,
        }
        self._asc = {}
        # Se precalculan aquí (en el hilo de trabajo) para que al pulsar
        # una cabecera no se note ninguna pausa.
        for columna in self.COLUMNAS_ORDENABLES:
            self.orden(columna, False)

    def __len__(self):
        return len(self.tamanos)

    def orden(self, columna, desc):
        """Lista de ids ordenada por la columna indicada (con caché)."""
        if columna not in self._asc:
            clave = self._claves[columna].__getitem__
            self._asc[columna] = sorted(range(len(self)), key=clave)
        asc = self._asc[columna]
        return asc[::-1] if desc else asc

    def filtrar(self, base, palabras):
        """Ids de `base` cuyo nombre contiene todas las palabras."""
        nn = self.nombres_norm
        return [i for i in base if all(p in nn[i] for p in palabras)]

    def sin_ruta(self, ruta):
        """Nuevo índice sin el archivo indicado (se usa tras borrarlo)."""
        return Indice([
            (t, r, f, os.path.basename(r))
            for t, r, f in zip(self.tamanos, self.rutas, self.fechas)
            if r != ruta
        ])


# ---------------------------------------------------------------- Interfaz
class SimpleCleaner(ctk.CTk):
    COLUMNAS = {
        "nombre": "Nombre",
        "tamano": "Tamaño",
        "ultimo_uso": "Última vez usado",
    }

    ESTADISTICAS = [
        ("revisados", "ARCHIVOS ENCONTRADOS"),
        ("carpetas", "CARPETAS REVISADAS"),
        ("total", "ESPACIO QUE OCUPAN"),
    ]

    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=FONDO)
        self.title("Simple Cleaner")
        self.geometry("980x760")
        self.minsize(820, 620)
        self._poner_icono()

        self.fuente_display, self.fuente_texto = self._elegir_fuentes()

        # Escaneo
        self.contadores = [(0, 0)] * N_HILOS
        self.resultado = None          # Indice creado por el hilo de escaneo
        self.indice = None             # Indice que se muestra actualmente
        self._escaneando = False
        self._carpetas = 0

        # Vista de la tabla
        self.vista = []                # ids visibles tras buscar y ordenar
        self.orden_col = "tamano"
        self.orden_desc = True
        self._busqueda_pendiente = None
        self._cache_busqueda = None    # (palabras, columna, desc, resultado)
        self._resultados_visibles = False
        self._decoracion = True        # formas del fondo (solo en la pantalla inicial)
        self._inicio = 0               # posición (en self.vista) de la primera fila visible
        self._filas_visibles = 20
        self._sel_pos = None           # posición seleccionada dentro de self.vista

        # Menú desplegable sobre el nombre de un archivo
        self._menu = None
        self._menu_iid = None
        self._pendiente = None

        # Diálogo de borrado
        self._overlay = None
        self._card = None
        self._btn_borrar = None
        self._barra_borrado = None
        self._cuenta_id = None
        self._restantes = 0
        self._fid_borrar = None
        self._ruta_borrar = ""
        self._nombre_borrar = ""
        self._tam_borrar = 0
        self._resultado_borrado = None

        self._crear_estilos()
        self._crear_widgets()

        # Cualquier clic fuera del menú lo cierra
        self.bind_all("<Button-1>", self._clic_global, add="+")

    # ---- Icono de la ventana
    def _poner_icono(self):
        try:
            self._icono_ventana = tk.PhotoImage(file=RUTA_LOGO)
            self.iconphoto(True, self._icono_ventana)
            if ES_WINDOWS:
                self.iconbitmap(RUTA_ICONO_WINDOWS)
        except Exception:
            traceback.print_exc()

    # ---- Fuentes
    def _elegir_fuentes(self):
        """
        Devuelve (fuente_display, fuente_texto):
        - display: Coolvetica para títulos y números.
        - texto: una variante fina del sistema para el resto de la app.
        """
        disponibles = set(tkfont.families(self))
        por_defecto = tkfont.nametofont("TkDefaultFont").actual("family")

        if NOMBRE_FUENTE_PROPIA in disponibles:
            display = NOMBRE_FUENTE_PROPIA
        else:
            display = next(
                (n for n in FUENTES_RESPALDO_TITULO if n in disponibles), por_defecto
            )

        texto = next((n for n in FUENTES_TEXTO_FINAS if n in disponibles), por_defecto)
        return display, texto

    def _fuente(self, tamano, display=False):
        """
        Fuente de la app en peso normal (Coolvetica Rg no tiene versiones más finas).
        display=True usa Coolvetica para títulos y números; el resto usa la fuente fina.
        """
        familia = self.fuente_display if display else self.fuente_texto
        return ctk.CTkFont(family=familia, size=tamano)

    # ---- Estilos de la tabla
    def _crear_estilos(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")

        # Sin bordes alrededor de la tabla
        estilo.layout("Moderno.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        estilo.configure(
            "Moderno.Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground="#E6E6E6",
            rowheight=ALTO_FILA,
            borderwidth=0,
            font=(self.fuente_texto, 11),
        )
        estilo.map(
            "Moderno.Treeview",
            background=[("selected", ROJO_SELECCION)],
            foreground=[("selected", "#FFFFFF")],
        )
        estilo.configure(
            "Moderno.Treeview.Heading",
            background=ELEVADO,
            foreground="#FFFFFF",
            font=(self.fuente_display, 11),
            relief="flat",
            borderwidth=0,
            padding=(12, 11),
        )
        estilo.map(
            "Moderno.Treeview.Heading",
            background=[("active", "#333333")],
        )

    # ---- Widgets
    def _crear_widgets(self):
        # Fondo decorativo (se crea primero para quedar detrás de todo)
        self.fondo = tk.Canvas(self, bg=FONDO, highlightthickness=0, bd=0)
        self.fondo.place(x=0, y=0, relwidth=1, relheight=1)
        self.fondo.bind("<Configure>", self._dibujar_fondo)

        # Zona de arriba: título + botón (al inicio centrada en la ventana)
        self.hero = ctk.CTkFrame(self, fg_color="transparent")
        self.hero.pack(expand=True)

        # Título en dos colores: SIMPLE (blanco) + CLEANER (rojo)
        self.fila_titulo = ctk.CTkFrame(self.hero, fg_color="transparent")
        self.fila_titulo.pack()
        self.titulo_a = ctk.CTkLabel(
            self.fila_titulo,
            text="SIMPLE",
            text_color=TEXTO,
            font=self._fuente(46, display=True),
        )
        self.titulo_a.pack(side="left")
        self.titulo_b = ctk.CTkLabel(
            self.fila_titulo,
            text=" CLEANER",
            text_color=ROJO,
            font=self._fuente(46, display=True),
        )
        self.titulo_b.pack(side="left")

        # Pulsar el título vuelve a la pantalla de inicio
        for etiqueta in (self.titulo_a, self.titulo_b):
            etiqueta.bind("<Button-1>", self._volver_inicio)
            try:
                etiqueta.configure(cursor="hand2")
            except Exception:
                pass

        self.subtitulo = ctk.CTkLabel(
            self.hero,
            text="Encuentra lo que más pesa y libera espacio en tu PC",
            text_color=TEXTO_SUAVE,
            font=self._fuente(15),
        )
        self.subtitulo.pack(pady=(2, 28))

        self.boton = ctk.CTkButton(
            self.hero,
            text="Escanear",
            command=self.iniciar_escaneo,
            width=220,
            height=50,
            corner_radius=12,
            fg_color=ROJO,
            hover_color=ROJO_HOVER,
            text_color="#FFFFFF",
            text_color_disabled="#F3B3B3",
            font=self._fuente(17),
            cursor="hand2",
        )
        self.boton.pack()

        self.progreso = ctk.CTkProgressBar(
            self.hero,
            mode="indeterminate",
            width=260,
            height=5,
            progress_color=ROJO,
            fg_color=ELEVADO,
        )

        self.estado = ctk.CTkLabel(
            self.hero,
            text="",
            text_color=TEXTO_SUAVE,
            font=self._fuente(14),
        )
        self.estado.pack(pady=(14, 0))

        # Tarjetas de estadísticas (se muestran al terminar el escaneo)
        self.stats = ctk.CTkFrame(self, fg_color="transparent")
        self.stats.grid_columnconfigure((0, 1, 2), weight=1, uniform="stat")
        self.valores = {}
        for col, (clave, titulo) in enumerate(self.ESTADISTICAS):
            tarjeta = ctk.CTkFrame(
                self.stats,
                fg_color=PANEL,
                corner_radius=12,
                border_width=1,
                border_color=BORDE,
            )
            tarjeta.grid(
                row=0,
                column=col,
                sticky="ew",
                padx=(0 if col == 0 else 6, 0 if col == 2 else 6),
            )
            ctk.CTkLabel(
                tarjeta,
                text=titulo,
                text_color=TEXTO_SUAVE,
                font=self._fuente(12),
            ).pack(anchor="w", padx=16, pady=(10, 0))
            valor = ctk.CTkLabel(
                tarjeta,
                text="-",
                text_color=ROJO if clave == "total" else TEXTO,
                font=self._fuente(24, display=True),
            )
            valor.pack(anchor="w", padx=16, pady=(0, 10))
            self.valores[clave] = valor

        # Barra de búsqueda: mismo ancho que la caja de resultados
        self.barra = ctk.CTkFrame(
            self,
            fg_color=ELEVADO,
            corner_radius=22,
            border_width=1,
            border_color=BORDE,
        )
        escala = max(1.0, self.winfo_fpixels("1i") / 96)

        def px(v):
            return v * escala

        lado = int(px(30))
        self.icono = tk.Canvas(
            self.barra,
            width=lado,
            height=lado,
            bg=ELEVADO,
            highlightthickness=0,
            bd=0,
            cursor="xterm",
        )
        # Lupa roja
        self.icono.create_oval(
            px(6), px(5), px(19), px(18), outline=ROJO, width=max(2, px(2.4))
        )
        self.icono.create_line(
            px(17.5), px(16.5), px(24), px(23),
            fill=ROJO, width=max(2, px(2.8)), capstyle="round",
        )
        self.icono.pack(side="left", padx=(16, 0), pady=7)

        self.contador = ctk.CTkLabel(
            self.barra,
            text="",
            anchor="e",
            text_color=TEXTO_SUAVE,
            font=self._fuente(13),
        )
        self.contador.pack(side="right", padx=(6, 18))

        self.caja_busqueda = ctk.CTkEntry(
            self.barra,
            placeholder_text="Buscar por nombre...",
            height=34,
            corner_radius=0,
            border_width=0,
            fg_color=ELEVADO,
            text_color=TEXTO,
            placeholder_text_color="#7A7A7A",
            font=self._fuente(15),
        )
        self.caja_busqueda.pack(side="left", fill="x", expand=True, padx=(6, 6), pady=7)

        self.caja_busqueda.bind("<KeyRelease>", self._al_escribir)
        self.caja_busqueda.bind("<Down>", self._bajar_desde_busqueda)
        self.caja_busqueda.bind(
            "<FocusIn>", lambda _e: self.barra.configure(border_color=ROJO)
        )
        self.caja_busqueda.bind(
            "<FocusOut>", lambda _e: self.barra.configure(border_color=BORDE)
        )
        self.icono.bind("<Button-1>", lambda _e: self.caja_busqueda.focus())

        # Tarjeta con la tabla de resultados
        self.tarjeta = ctk.CTkFrame(
            self,
            fg_color=PANEL,
            border_width=1,
            border_color=BORDE,
            corner_radius=14,
        )
        contenedor = tk.Frame(self.tarjeta, bg=PANEL)
        contenedor.pack(fill="both", expand=True, padx=10, pady=10)

        # La tabla solo crea las filas visibles; el scroll se gestiona a mano.
        self.tabla = ttk.Treeview(
            contenedor,
            columns=tuple(self.COLUMNAS),
            show="headings",
            style="Moderno.Treeview",
            selectmode="browse",
        )
        self.scroll = ctk.CTkScrollbar(
            contenedor,
            command=self._desplazar,
            fg_color=PANEL,
            button_color="#444444",
            button_hover_color=ROJO,
        )

        anclas = {"nombre": "w", "tamano": "e", "ultimo_uso": "center"}
        anchos = {"nombre": 440, "tamano": 130, "ultimo_uso": 190}
        for col, texto in self.COLUMNAS.items():
            self.tabla.heading(
                col,
                text=texto,
                anchor=anclas[col],
                command=lambda c=col: self.ordenar_por(c),
            )
            self.tabla.column(
                col, width=anchos[col], anchor=anclas[col], stretch=(col == "nombre")
            )

        # Los archivos de 1 GB o más se destacan en rojo
        self.tabla.tag_configure("grande", foreground=ROJO_CLARO)

        self.tabla.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y", padx=(6, 0))

        self._conectar_eventos_tabla()

        self.pie = ctk.CTkLabel(
            self,
            text="Clic en una columna para ordenar  ·  Clic en un nombre para ver opciones  ·  Flechas para navegar",
            text_color=TEXTO_SUAVE,
            font=self._fuente(13),
        )

    def _conectar_eventos_tabla(self):
        t = self.tabla
        t.bind("<Button-1>", self._clic_tabla)
        t.bind("<Return>", self._menu_teclado)
        t.bind("<Escape>", lambda _e: self._cerrar_menu())
        t.bind("<<TreeviewSelect>>", self._al_seleccionar)
        t.bind("<Configure>", lambda _e: self._renderizar())
        t.bind("<MouseWheel>", self._rueda)
        t.bind("<Button-4>", lambda _e: self._desplazar_filas(-PASO_RUEDA))
        t.bind("<Button-5>", lambda _e: self._desplazar_filas(PASO_RUEDA))
        t.bind("<Up>", lambda _e: self._mover(-1))
        t.bind("<Down>", lambda _e: self._mover(1))
        t.bind("<Prior>", lambda _e: self._mover(-self._filas_visibles))
        t.bind("<Next>", lambda _e: self._mover(self._filas_visibles))
        t.bind("<Home>", lambda _e: self._ir_a(0))
        t.bind("<End>", lambda _e: self._ir_a(len(self.vista) - 1))

    # ---- Fondo decorativo
    def _dibujar_fondo(self, _evento=None):
        c = self.fondo
        c.delete("decor")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return

        # Formas de flechas (">>") a los lados, solo en la pantalla inicial
        margen = (w - 520) / 2
        if self._decoracion and margen > 70:
            u = margen / 2.2
            profundidad, grosor = u * 0.9, u * 0.55
            y0, y1 = h * 0.10, h * 0.90
            ym = (y0 + y1) / 2
            colores = ("#191919", "#1D1D1D")
            for k, color in enumerate(colores):
                x = w - margen + k * u * 1.15
                puntos = [
                    (x, y0), (x + profundidad, ym), (x, y1),
                    (x + grosor, y1), (x + grosor + profundidad, ym), (x + grosor, y0),
                ]
                derecha = [coord for p in puntos for coord in p]
                izquierda = [coord for p in puntos for coord in (w - p[0], p[1])]
                c.create_polygon(derecha, fill=color, outline="", tags="decor")
                c.create_polygon(izquierda, fill=color, outline="", tags="decor")

        # Detalle rojo en el borde inferior
        c.create_oval(
            w * 0.32, h - 9, w * 0.68, h + 34,
            fill=ROJO_OSCURO, outline="", tags="decor",
        )

    # ---- Pantalla de inicio
    def _volver_inicio(self, _e=None):
        if self._escaneando or self._overlay is not None:
            return

        self._cerrar_menu()
        self.indice = None
        self.resultado = None
        self.vista = []
        self._cache_busqueda = None
        self._sel_pos = None
        self._inicio = 0
        self.tabla.delete(*self.tabla.get_children())
        self.contador.configure(text="")
        if self.caja_busqueda.get():
            self.caja_busqueda.delete(0, "end")

        # Ocultar resultados y restaurar la vista inicial
        self.stats.pack_forget()
        self.tarjeta.pack_forget()
        self.barra.pack_forget()
        self.pie.pack_forget()

        self.hero.pack_configure(expand=True, pady=0)
        self.titulo_a.configure(font=self._fuente(46, display=True))
        self.titulo_b.configure(font=self._fuente(46, display=True))
        self.subtitulo.pack(pady=(2, 28), before=self.boton)
        self.boton.configure(
            state="normal", text="Escanear", width=220, height=50, corner_radius=12
        )

        self._resultados_visibles = False
        self._decoracion = True
        self._dibujar_fondo()

    # ---- Escaneo
    def iniciar_escaneo(self):
        self._escaneando = True
        self.boton.configure(state="disabled", text="Escaneando...")
        self.contadores = [(0, 0)] * N_HILOS
        self.resultado = None

        self.estado.configure(text="")
        self.estado.pack(pady=(14, 0))
        self.progreso.pack(pady=(18, 0), before=self.estado)
        self.progreso.start()

        threading.Thread(target=self._trabajo_escaneo, daemon=True).start()
        self._actualizar_progreso()

    def _trabajo_escaneo(self):
        try:
            registros = escanear(carpetas_a_escanear(), self.contadores)
            self.resultado = Indice(registros)
        except Exception:
            traceback.print_exc()
            self.resultado = Indice([])

    def _actualizar_progreso(self):
        if self.resultado is None:
            archivos = sum(c[0] for c in self.contadores)
            self.estado.configure(text=f"{formatear_numero(archivos)} archivos revisados")
            self.after(120, self._actualizar_progreso)
        else:
            self._mostrar_resultados()

    # ---- Resultados
    def _mostrar_resultados(self):
        self._escaneando = False
        self.progreso.stop()
        self.progreso.pack_forget()
        self.estado.pack_forget()

        # Compactar la parte de arriba y mostrar el panel de resultados
        self.hero.pack_configure(expand=False, pady=(18, 6))
        self.titulo_a.configure(font=self._fuente(30, display=True))
        self.titulo_b.configure(font=self._fuente(30, display=True))
        self.subtitulo.pack_forget()
        self.boton.configure(
            state="normal", text="Escanear", width=170, height=40, corner_radius=10
        )

        if not self._resultados_visibles:
            self.stats.pack(fill="x", padx=28, pady=(4, 10))
            self.tarjeta.pack(fill="both", expand=True, padx=28, pady=(0, 6))
            self.barra.pack(fill="x", padx=28, pady=(0, 10), before=self.tarjeta)
            self.pie.pack(pady=(0, 20))
            self._resultados_visibles = True
            self._decoracion = False
            self._dibujar_fondo()

        self.indice = self.resultado
        self._carpetas = sum(c[1] for c in self.contadores)

        # Vaciar la búsqueda solo si hay texto escrito (así el texto de ayuda
        # no se borra) y dejar el foco en la tabla.
        if self.caja_busqueda.get():
            self.caja_busqueda.delete(0, "end")
        self.tabla.focus_set()

        self._actualizar_estadisticas()

        # El resultado inicial va de mayor a menor tamaño
        self.orden_col = "tamano"
        self.orden_desc = True
        self._aplicar_filtro()
        self._actualizar_cabeceras()

    def _actualizar_estadisticas(self):
        if self.indice is None:
            return
        self.valores["revisados"].configure(text=formatear_numero(len(self.indice)))
        self.valores["carpetas"].configure(text=formatear_numero(self._carpetas))
        self.valores["total"].configure(text=formatear_tamano(self.indice.total_bytes))

    # ---- Búsqueda
    @staticmethod
    def _es_ampliacion(anteriores, nuevas):
        """
        True si cada palabra anterior está contenida en alguna palabra nueva.
        En ese caso, los resultados nuevos son un subconjunto de los anteriores
        y basta con filtrar sobre ellos.
        """
        return all(any(a in n for n in nuevas) for a in anteriores)

    def _aplicar_filtro(self):
        if self.indice is None:
            return

        palabras = tuple(normalizar(self.caja_busqueda.get()).split())
        columna, desc = self.orden_col, self.orden_desc
        base = self.indice.orden(columna, desc)

        if palabras:
            cache = self._cache_busqueda
            if (
                cache is not None
                and cache[1] == columna
                and cache[2] == desc
                and self._es_ampliacion(cache[0], palabras)
            ):
                base = cache[3]    # solo buscamos dentro de lo ya filtrado

            self.vista = self.indice.filtrar(base, palabras)
            self._cache_busqueda = (palabras, columna, desc, self.vista)
            self.contador.configure(text=f"{len(self.vista)} de {len(self.indice)}")
        else:
            self.vista = base
            self._cache_busqueda = None
            self.contador.configure(text="")

        self._inicio = 0
        self._sel_pos = None
        self._renderizar()

    def _al_escribir(self, _evento=None):
        if self._busqueda_pendiente is not None:
            self.after_cancel(self._busqueda_pendiente)
        self._busqueda_pendiente = self.after(ESPERA_BUSQUEDA_MS, self._aplicar_busqueda)

    def _aplicar_busqueda(self):
        self._busqueda_pendiente = None
        self._aplicar_filtro()

    def _bajar_desde_busqueda(self, _e=None):
        self.tabla.focus_set()
        self._mover(1)
        return "break"

    # ---- Ordenar al hacer clic en una columna
    def ordenar_por(self, columna):
        if columna == self.orden_col:
            self.orden_desc = not self.orden_desc      # alternar
        else:
            self.orden_col = columna
            # Tamaño y fecha empiezan de mayor a menor, el nombre de A a Z
            self.orden_desc = columna != "nombre"
        self._aplicar_filtro()
        self._actualizar_cabeceras()

    def _actualizar_cabeceras(self):
        for col, texto in self.COLUMNAS.items():
            if col == self.orden_col:
                flecha = "  ▼" if self.orden_desc else "  ▲"
            else:
                flecha = ""
            self.tabla.heading(col, text=texto + flecha)

    # ---- Tabla virtual: solo se dibujan las filas visibles
    def _renderizar(self):
        self._cerrar_menu()            # si la tabla se mueve, el menú deja de cuadrar
        if self.indice is None:
            return

        total = len(self.vista)
        self._filas_visibles = max(1, (self.tabla.winfo_height() - ALTO_CABECERA) // ALTO_FILA)
        n = self._filas_visibles
        self._inicio = max(0, min(self._inicio, total - n))
        fin = min(total, self._inicio + n)

        idx = self.indice
        self.tabla.delete(*self.tabla.get_children())
        for pos in range(self._inicio, fin):
            fid = self.vista[pos]
            tam = idx.tamanos[fid]
            ruta = idx.rutas[fid]
            self.tabla.insert(
                "",
                "end",
                iid=str(fid),
                values=(
                    os.path.basename(ruta) or ruta,
                    formatear_tamano(tam),
                    formatear_fecha(idx.fechas[fid]),
                ),
                tags=("grande",) if tam >= UN_GB else (),
            )

        # Mantener la selección si su fila sigue visible
        if self._sel_pos is not None and self._inicio <= self._sel_pos < fin:
            self.tabla.selection_set(str(self.vista[self._sel_pos]))

        if total:
            self.scroll.set(self._inicio / total, fin / total)
        else:
            self.scroll.set(0, 1)

    def _desplazar(self, *args):
        """Comando de la barra de scroll."""
        total = len(self.vista)
        if args[0] == "moveto":
            self._inicio = int(float(args[1]) * total)
        elif args[0] == "scroll":
            paso = self._filas_visibles if args[2] == "pages" else 1
            self._inicio += int(args[1]) * paso
        self._renderizar()

    def _desplazar_filas(self, delta):
        self._inicio += delta
        self._renderizar()
        return "break"

    def _rueda(self, e):
        if e.delta == 0:
            return "break"
        return self._desplazar_filas(-PASO_RUEDA if e.delta > 0 else PASO_RUEDA)

    def _al_seleccionar(self, _e=None):
        sel = self.tabla.selection()
        if sel:
            self._sel_pos = self._inicio + self.tabla.index(sel[0])

    def _mover(self, delta):
        total = len(self.vista)
        if not total:
            return "break"
        if self._sel_pos is None:
            nuevo = 0 if delta > 0 else total - 1
        else:
            nuevo = min(max(self._sel_pos + delta, 0), total - 1)
        self._seleccionar_pos(nuevo)
        return "break"

    def _ir_a(self, pos):
        if self.vista:
            self._seleccionar_pos(pos)
        return "break"

    def _seleccionar_pos(self, pos):
        n = self._filas_visibles
        if pos < self._inicio:
            self._inicio = pos
        elif pos >= self._inicio + n:
            self._inicio = pos - n + 1
        self._sel_pos = pos
        self._renderizar()

    # ---- Menú desplegable sobre el nombre del archivo
    def _clic_tabla(self, evento):
        # Solo los clics en la columna del nombre abren el menú
        if self.tabla.identify_column(evento.x) != "#1":
            return
        iid = self.tabla.identify_row(evento.y)
        if not iid:
            return
        # Si el menú ya estaba abierto para esta fila, el clic lo cierra.
        # El clic global (que se ejecuta justo después) cierra el menú y
        # la apertura se hace al final, cuando el evento ya terminó.
        self._pendiente = None if self._menu_iid == iid else iid
        self.after_idle(self._abrir_pendiente)

    def _abrir_pendiente(self):
        iid, self._pendiente = self._pendiente, None
        if iid:
            self._abrir_menu(iid)

    def _menu_teclado(self, _e=None):
        sel = self.tabla.selection()
        if sel:
            self._abrir_menu(sel[0])
        return "break"

    def _clic_global(self, evento):
        if self._menu is None:
            return
        try:
            ruta_widget = str(evento.widget)
        except Exception:
            ruta_widget = ""
        # Clics dentro del propio menú: dejar que sus botones actúen
        if (ruta_widget + ".").startswith(str(self._menu) + "."):
            return
        self._cerrar_menu()

    def _abrir_menu(self, iid):
        self._cerrar_menu()
        if self._overlay is not None or self.indice is None:
            return

        bbox = self.tabla.bbox(iid, "#1")
        if not bbox:                   # fila no visible
            return
        x, y, _ancho_celda, alto_celda = bbox

        menu = ctk.CTkFrame(
            self,
            fg_color=ELEVADO,
            corner_radius=10,
            border_width=1,
            border_color=BORDE,
        )
        ctk.CTkButton(
            menu,
            text="Abrir ubicación",
            width=194,
            height=38,
            corner_radius=8,
            fg_color="transparent",
            hover_color="#333333",
            text_color=TEXTO,
            font=self._fuente(14),
            command=lambda: self._accion_menu("abrir"),
        ).pack(padx=8, pady=(8, 0))
        ctk.CTkButton(
            menu,
            text="Borrar",
            width=194,
            height=38,
            corner_radius=8,
            fg_color="transparent",
            hover_color="#3A1515",
            text_color=ROJO_CLARO,
            font=self._fuente(14),
            command=lambda: self._accion_menu("borrar"),
        ).pack(padx=8, pady=(2, 8))

        self._menu = menu
        self._menu_iid = iid

        # Colocar el menú justo debajo de la celda del nombre
        menu.update_idletasks()
        ancho = menu.winfo_reqwidth()
        alto = menu.winfo_reqheight()
        x_raiz = self.tabla.winfo_rootx() + x - self.winfo_rootx()
        y_raiz = self.tabla.winfo_rooty() + y + alto_celda - self.winfo_rooty() + 4
        x_raiz = max(8, min(x_raiz, self.winfo_width() - ancho - 8))
        if y_raiz + alto > self.winfo_height() - 8:
            # No hay sitio debajo: se despliega hacia arriba
            y_raiz = self.tabla.winfo_rooty() + y - self.winfo_rooty() - alto - 4
        menu.place(x=x_raiz, y=y_raiz)

    def _cerrar_menu(self):
        if self._menu is not None:
            self._menu.destroy()
            self._menu = None
            self._menu_iid = None

    def _accion_menu(self, accion):
        iid = self._menu_iid
        self._cerrar_menu()
        if iid is None or self.indice is None:
            return
        fid = int(iid)
        if accion == "abrir":
            abrir_ubicacion(self.indice.rutas[fid])
        else:
            self._confirmar_borrado(fid)

    # ---- Diálogo de borrado (superposición modal)
    def _confirmar_borrado(self, fid):
        if self.indice is None or self._overlay is not None:
            return

        self._fid_borrar = fid
        self._ruta_borrar = self.indice.rutas[fid]
        self._nombre_borrar = os.path.basename(self._ruta_borrar) or self._ruta_borrar
        self._tam_borrar = self.indice.tamanos[fid]

        self._overlay = ctk.CTkFrame(self, fg_color=FONDO_MODAL, corner_radius=0)
        self._overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._card = ctk.CTkFrame(
            self._overlay,
            fg_color=PANEL,
            border_width=1,
            border_color=BORDE,
            corner_radius=16,
        )
        self._card.place(relx=0.5, rely=0.5, anchor="center")
        self._pintar_confirmacion()

    def _limpiar_tarjeta(self):
        for w in self._card.winfo_children():
            w.destroy()

    def _pintar_confirmacion(self):
        self._limpiar_tarjeta()
        tarjeta = self._card

        ctk.CTkLabel(
            tarjeta,
            text="¿Seguro que quieres borrar?",
            text_color=TEXTO,
            font=self._fuente(24, display=True),
        ).pack(anchor="w", padx=28, pady=(24, 10))

        ctk.CTkLabel(
            tarjeta,
            text=self._nombre_borrar,
            text_color=ROJO_CLARO,
            font=self._fuente(16),
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=28)

        ctk.CTkLabel(
            tarjeta,
            text=self._ruta_borrar,
            text_color=TEXTO_SUAVE,
            font=self._fuente(12),
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(2, 14))

        ctk.CTkLabel(
            tarjeta,
            text="El archivo se eliminará de forma permanente y no irá a la papelera.",
            text_color=TEXTO_SUAVE,
            font=self._fuente(14),
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(0, 22))

        fila = ctk.CTkFrame(tarjeta, fg_color="transparent")
        fila.pack(fill="x", padx=28, pady=(0, 26))

        ctk.CTkButton(
            fila,
            text="Cancelar",
            width=130,
            height=44,
            corner_radius=10,
            fg_color=ELEVADO,
            hover_color="#333333",
            text_color=TEXTO,
            font=self._fuente(15),
            command=self._cerrar_dialogo,
        ).pack(side="left")

        # Botón de borrar: desactivado hasta que termina la cuenta atrás
        self._btn_borrar = ctk.CTkButton(
            fila,
            text=f"Borrar ({CUENTA_ATRAS})",
            width=260,
            height=44,
            corner_radius=10,
            state="disabled",
            fg_color=ROJO_OSCURO,
            hover_color=ROJO_OSCURO,
            text_color="#F3B3B3",
            text_color_disabled="#F3B3B3",
            font=self._fuente(15),
            command=self._borrar,
        )
        self._btn_borrar.pack(side="right", padx=(14, 0))

        self._restantes = CUENTA_ATRAS
        self._cancelar_cuenta()
        self._cuenta_id = self.after(1000, self._tick_cuenta)

    def _tick_cuenta(self):
        self._cuenta_id = None
        if self._btn_borrar is None:
            return
        self._restantes -= 1
        if self._restantes > 0:
            self._btn_borrar.configure(text=f"Borrar ({self._restantes})")
            self._cuenta_id = self.after(1000, self._tick_cuenta)
        else:
            self._btn_borrar.configure(
                text="Borrar",
                state="normal",
                fg_color=ROJO,
                hover_color=ROJO_HOVER,
                text_color="#FFFFFF",
            )

    def _cancelar_cuenta(self):
        if self._cuenta_id is not None:
            self.after_cancel(self._cuenta_id)
            self._cuenta_id = None

    def _cerrar_dialogo(self):
        self._cancelar_cuenta()
        if self._overlay is not None:
            self._overlay.destroy()
        self._overlay = None
        self._card = None
        self._btn_borrar = None
        self._barra_borrado = None
        self.tabla.focus_set()

    def _borrar(self):
        if self._restantes > 0 or self._btn_borrar is None:
            return
        self._cancelar_cuenta()
        self._pintar_borrando()

    def _pintar_borrando(self):
        self._limpiar_tarjeta()
        self._btn_borrar = None
        tarjeta = self._card

        ctk.CTkLabel(
            tarjeta,
            text="Borrando...",
            text_color=TEXTO,
            font=self._fuente(24, display=True),
        ).pack(anchor="w", padx=28, pady=(26, 6))

        ctk.CTkLabel(
            tarjeta,
            text=self._nombre_borrar,
            text_color=TEXTO_SUAVE,
            font=self._fuente(14),
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=28)

        self._barra_borrado = ctk.CTkProgressBar(
            tarjeta,
            mode="indeterminate",
            width=460,
            height=8,
            progress_color=ROJO,
            fg_color=ELEVADO,
        )
        self._barra_borrado.pack(padx=28, pady=(20, 28))
        self._barra_borrado.start()

        self._resultado_borrado = None
        threading.Thread(
            target=self._trabajo_borrado,
            args=(self._ruta_borrar, self.indice),
            daemon=True,
        ).start()
        self.after(100, self._esperar_borrado)

    def _trabajo_borrado(self, ruta, indice):
        """Hilo secundario: borra el archivo y prepara el índice actualizado."""
        try:
            try:
                os.remove(ruta)
            except FileNotFoundError:
                self._resultado_borrado = (False, "El archivo ya no existe en esa ubicación.", None)
                return
            except PermissionError:
                self._resultado_borrado = (
                    False,
                    "No tienes permiso para borrarlo o está abierto en otro programa.",
                    None,
                )
                return
            except OSError as e:
                self._resultado_borrado = (False, f"Error del sistema: {e.strerror or e}", None)
                return

            self._resultado_borrado = (True, "", indice.sin_ruta(ruta))
        except Exception as e:
            traceback.print_exc()
            self._resultado_borrado = (False, f"Error inesperado: {e}", None)

    def _esperar_borrado(self):
        if self._resultado_borrado is None:
            self.after(100, self._esperar_borrado)
            return

        ok, msg, nuevo = self._resultado_borrado
        if self._barra_borrado is not None:
            self._barra_borrado.stop()
        self._barra_borrado = None

        if ok:
            self.indice = nuevo
            self._cache_busqueda = None
            self._sel_pos = None
            self._actualizar_estadisticas()
            self._aplicar_filtro()

        self._pintar_resultado(ok, msg)

    def _pintar_resultado(self, ok, msg):
        self._limpiar_tarjeta()
        tarjeta = self._card

        if ok:
            titulo, color = "Archivo borrado", VERDE
            detalle = (
                f"«{self._nombre_borrar}» se ha borrado correctamente.\n"
                f"Has liberado {formatear_tamano(self._tam_borrar)} de espacio."
            )
        else:
            titulo, color = "No se pudo borrar", ROJO_CLARO
            detalle = f"«{self._nombre_borrar}» no se ha borrado.\n{msg}"

        ctk.CTkLabel(
            tarjeta,
            text=titulo,
            text_color=color,
            font=self._fuente(24, display=True),
        ).pack(anchor="w", padx=28, pady=(24, 8))

        ctk.CTkLabel(
            tarjeta,
            text=detalle,
            text_color=TEXTO,
            font=self._fuente(14),
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(0, 22))

        ctk.CTkButton(
            tarjeta,
            text="Cerrar",
            height=44,
            corner_radius=10,
            fg_color=ELEVADO,
            hover_color="#333333",
            text_color=TEXTO,
            font=self._fuente(15),
            command=self._cerrar_dialogo,
        ).pack(fill="x", padx=28, pady=(0, 26))


if __name__ == "__main__":
    # Registrar la fuente antes de crear la ventana
    cargar_fuente_propia(RUTA_FUENTE_PROPIA)
    SimpleCleaner().mainloop()