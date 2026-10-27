"""
Simple Cleaner
--------------
Simple app to find the files that take up the most space on your PC
and decide which ones to delete.

Requirements: Python 3.8+ and customtkinter
    python -m pip install customtkinter

Run:
    python SimpleCleanerEN.py
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

# ---------------------------------------------------------------- Theme
# Dark palette with a red accent (inspired by the ExitLag style)
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

# ---------------------------------------------------------------- Fonts
# Coolvetica (Typodermic) is loaded from the script folder, without installing it.
# Personal use: do not include the .otf if you distribute the app (see EULA).
NOMBRE_FUENTE_PROPIA = "Coolvetica"
RUTA_FUENTE_PROPIA = os.path.join(CARPETA_APP, "Coolvetica Rg.otf")

# For titles and numbers: if Coolvetica fails to load, the first available font in this list is used.
FUENTES_RESPALDO_TITULO = [
    "Varela Round",
    "Nunito",
    "Quicksand",
    "Arial Rounded MT Bold",
]

# For the rest of the text, thin system font variants are preferred.
FUENTES_TEXTO_FINAS = [
    "Segoe UI Light",       # Windows
    "Helvetica Neue Light", # macOS
    "Ubuntu Light",         # Linux
    "Segoe UI",
    "Helvetica Neue",
    "Arial",
]

# Parallel scan: several threads walking folders at the same time.
N_HILOS = min(32, (os.cpu_count() or 4) * 4)

# Table: height of each row, approximate header height and rows per wheel step.
ALTO_FILA = 38
ALTO_CABECERA = 40
PASO_RUEDA = 3

# Delay (ms) after the last keystroke before filtering.
ESPERA_BUSQUEDA_MS = 120

# Countdown seconds before a deletion can be confirmed.
CUENTA_ATRAS = 5

ES_WINDOWS = platform.system() == "Windows"
ATRIBUTO_REPARSE = 0x400  # Windows: junctions and special links

UN_GB = 1024 ** 3

# Strips accents and diaereses, including the decomposed forms (macOS uses NFD).
TABLA_SIN_TILDES = str.maketrans(
    "áàäâãéèëêíìïîóòöôõúùüûñç",
    "aaaaaeeeeiiiiooooouuuunc",
    "\u0300\u0301\u0302\u0303\u0308",
)

# ---------------------------------------------------------------- Icon
# Logo used as the window icon. Searched in this order.
RUTAS_LOGO = [
    os.path.join(CARPETA_APP, "Simple_Cleaner_Logo_NOBG_1.png"),
    os.path.join(CARPETA_APP, "Simple_Cleaner_Logo_NOBG.png"),
]
RUTA_LOGO = next((r for r in RUTAS_LOGO if os.path.isfile(r)), None)
RUTA_ICONO_WINDOWS = os.path.join(CARPETA_APP, "Simple_Cleaner_Logo_NOBG.ico")

# Icon background color. None = logo as is, with a transparent background.
# If the title bar or taskbar is light, the white S won't be visible:
# in that case set a color, for example "#141414".
COLOR_FONDO_ICONO = None

# Bold fonts for the fallback icon (in order of preference).
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
        return ImageFont.load_default(size=tamano)   # Pillow 10.1 or newer
    except TypeError:
        return ImageFont.load_default()


def _quitar_fondo_blanco(imagen):
    """
    If the PNG has no real transparency (opaque white background), turns
    almost-white pixels transparent.
    """
    if imagen.getchannel("A").getextrema()[0] != 255:
        return imagen                       # already has transparency

    pixeles = [
        (r, g, b, 0) if (r > 245 and g > 245 and b > 245) else (r, g, b, a)
        for r, g, b, a in imagen.getdata()
    ]
    imagen.putdata(pixeles)
    return imagen


def _icono_desde_logo(tamano):
    """Uses the logo as the icon, filling almost the whole square."""
    from PIL import Image, ImageDraw

    logo = Image.open(RUTA_LOGO).convert("RGBA")
    logo = _quitar_fondo_blanco(logo)

    # Crop transparent borders so the logo fills the space
    caja = logo.split()[-1].getbbox()
    if caja:
        logo = logo.crop(caja)

    # Scale the logo keeping proportions, with a small margin
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
    """Fallback icon: rounded dark background, a white S and a red C."""
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

    # Center the "SC" pair in the icon
    x = (tamano - (ancho_s + separacion + ancho_c)) // 2
    y = (tamano - alto) // 2

    draw.text((x - caja_s[0], y - caja_s[1]), "S", font=fuente, fill="#FFFFFF")
    x_c = x + ancho_s + separacion
    draw.text((x_c - caja_c[0], y - caja_c[1]), "C", font=fuente, fill=ROJO)
    return img


def crear_icono(tamano=256):
    """Returns the app icon: the logo if it exists, or the drawn fallback."""
    if RUTA_LOGO:
        try:
            return _icono_desde_logo(tamano)
        except Exception:
            traceback.print_exc()
    return _icono_dibujado(tamano)


# ---------------------------------------------------------------- Logic
def cargar_fuente_propia(ruta):
    """
    Registers a font file for this program only, without installing it
    on the system. Returns True if it was registered successfully.
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
    """Returns the folders to scan depending on the operating system."""
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
    """Converts bytes to readable text (GB, MB, KB)."""
    gb = num_bytes / UN_GB
    if gb >= 1:
        return f"{gb:.2f} GB"
    mb = num_bytes / (1024 ** 2)
    if mb >= 1:
        return f"{mb:.1f} MB"
    return f"{num_bytes / 1024:.0f} KB"


def formatear_fecha(timestamp):
    try:
        return datetime.fromtimestamp(timestamp).strftime("%m/%d/%Y  %H:%M")
    except (OverflowError, OSError, ValueError):
        return "Unknown"


def formatear_numero(n):
    """12345 -> '12,345'"""
    return f"{n:,}"


def normalizar(texto):
    """Lowercase and accent-free, so 'Música' matches 'musica'."""
    return texto.lower().translate(TABLA_SIN_TILDES)


def escanear(carpetas, contadores):
    """
    Walks the folders with several threads at once and returns ALL the
    files found as tuples (size, path, last_used, name).

    `contadores` is a list (one slot per thread) of tuples
    (files, folders) that keep being updated to show progress.
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
            if carpeta is None:      # end signal
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
                                if archivos & 2047 == 0:   # progress every 2048
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

    cola.join()                      # wait until no folder is left
    for _ in hilos:
        cola.put(None)
    for h in hilos:
        h.join()

    return list(itertools.chain.from_iterable(listas))


def abrir_ubicacion(ruta):
    """Opens the file explorer showing the selected file."""
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
    Stores the files in parallel lists (one list per field) instead of
    one object per file: it uses far less memory and sorting or filtering
    is faster. Each file is identified by its position (its id).
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
        # Precomputed here (in the worker thread) so clicking a header
        # causes no noticeable pause.
        for columna in self.COLUMNAS_ORDENABLES:
            self.orden(columna, False)

    def __len__(self):
        return len(self.tamanos)

    def orden(self, columna, desc):
        """List of ids sorted by the given column (cached)."""
        if columna not in self._asc:
            clave = self._claves[columna].__getitem__
            self._asc[columna] = sorted(range(len(self)), key=clave)
        asc = self._asc[columna]
        return asc[::-1] if desc else asc

    def filtrar(self, base, palabras):
        """Ids from `base` whose name contains all the words."""
        nn = self.nombres_norm
        return [i for i in base if all(p in nn[i] for p in palabras)]

    def sin_ruta(self, ruta):
        """New index without the given file (used after deleting it)."""
        return Indice([
            (t, r, f, os.path.basename(r))
            for t, r, f in zip(self.tamanos, self.rutas, self.fechas)
            if r != ruta
        ])


# ---------------------------------------------------------------- Interface
class SimpleCleaner(ctk.CTk):
    COLUMNAS = {
        "nombre": "Name",
        "tamano": "Size",
        "ultimo_uso": "Last used",
    }

    ESTADISTICAS = [
        ("revisados", "FILES FOUND"),
        ("carpetas", "FOLDERS SCANNED"),
        ("total", "SPACE USED"),
    ]

    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=FONDO)
        self.title("Simple Cleaner")
        self.geometry("980x760")
        self.minsize(820, 620)
        self._poner_icono()

        self.fuente_display, self.fuente_texto = self._elegir_fuentes()

        # Scan
        self.contadores = [(0, 0)] * N_HILOS
        self.resultado = None          # Index created by the scan thread
        self.indice = None             # Index currently displayed
        self._escaneando = False
        self._carpetas = 0

        # Table view
        self.vista = []                # ids visible after searching and sorting
        self.orden_col = "tamano"
        self.orden_desc = True
        self._busqueda_pendiente = None
        self._cache_busqueda = None    # (palabras, columna, desc, resultado)
        self._resultados_visibles = False
        self._decoracion = True        # background shapes (start screen only)
        self._inicio = 0               # position (in self.vista) of the first visible row
        self._filas_visibles = 20
        self._sel_pos = None           # selected position within self.vista

        # Dropdown menu over a file name
        self._menu = None
        self._menu_iid = None
        self._pendiente = None

        # Delete dialog
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

        # Any click outside the menu closes it
        self.bind_all("<Button-1>", self._clic_global, add="+")

    # ---- Window icon
    def _poner_icono(self):
        try:
            self._icono_ventana = tk.PhotoImage(file=RUTA_LOGO)
            self.iconphoto(True, self._icono_ventana)
            if ES_WINDOWS:
                self.iconbitmap(RUTA_ICONO_WINDOWS)
        except Exception:
            traceback.print_exc()

    # ---- Fonts
    def _elegir_fuentes(self):
        """
        Returns (display_font, text_font):
        - display: Coolvetica for titles and numbers.
        - text: a thin system variant for the rest of the app.
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
        App font at normal weight (Coolvetica Rg has no thinner versions).
        display=True uses Coolvetica for titles and numbers; the rest uses the thin font.
        """
        familia = self.fuente_display if display else self.fuente_texto
        return ctk.CTkFont(family=familia, size=tamano)

    # ---- Table styles
    def _crear_estilos(self):
        estilo = ttk.Style(self)
        estilo.theme_use("clam")

        # No borders around the table
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
        # Decorative background (created first so it stays behind everything)
        self.fondo = tk.Canvas(self, bg=FONDO, highlightthickness=0, bd=0)
        self.fondo.place(x=0, y=0, relwidth=1, relheight=1)
        self.fondo.bind("<Configure>", self._dibujar_fondo)

        # Top area: title + button (centered in the window at the start)
        self.hero = ctk.CTkFrame(self, fg_color="transparent")
        self.hero.pack(expand=True)

        # Two-color title: SIMPLE (white) + CLEANER (red)
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

        # Clicking the title goes back to the start screen
        for etiqueta in (self.titulo_a, self.titulo_b):
            etiqueta.bind("<Button-1>", self._volver_inicio)
            try:
                etiqueta.configure(cursor="hand2")
            except Exception:
                pass

        self.subtitulo = ctk.CTkLabel(
            self.hero,
            text="Find what weighs the most and free up space on your PC",
            text_color=TEXTO_SUAVE,
            font=self._fuente(15),
        )
        self.subtitulo.pack(pady=(2, 28))

        self.boton = ctk.CTkButton(
            self.hero,
            text="Scan",
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

        # Stat cards (shown when the scan finishes)
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

        # Search bar: same width as the results box
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
        # Red magnifier
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
            placeholder_text="Search by name...",
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

        # Card with the results table
        self.tarjeta = ctk.CTkFrame(
            self,
            fg_color=PANEL,
            border_width=1,
            border_color=BORDE,
            corner_radius=14,
        )
        contenedor = tk.Frame(self.tarjeta, bg=PANEL)
        contenedor.pack(fill="both", expand=True, padx=10, pady=10)

        # The table only creates the visible rows; scrolling is handled manually.
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

        # Files of 1 GB or more are highlighted in red
        self.tabla.tag_configure("grande", foreground=ROJO_CLARO)

        self.tabla.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y", padx=(6, 0))

        self._conectar_eventos_tabla()

        self.pie = ctk.CTkLabel(
            self,
            text="Click a column to sort  ·  Click a name for options  ·  Arrow keys to navigate",
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

    # ---- Decorative background
    def _dibujar_fondo(self, _evento=None):
        c = self.fondo
        c.delete("decor")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return

        # Arrow shapes (">>") on the sides, start screen only
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

        # Red detail on the bottom edge
        c.create_oval(
            w * 0.32, h - 9, w * 0.68, h + 34,
            fill=ROJO_OSCURO, outline="", tags="decor",
        )

    # ---- Start screen
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

        # Hide results and restore the initial view
        self.stats.pack_forget()
        self.tarjeta.pack_forget()
        self.barra.pack_forget()
        self.pie.pack_forget()

        self.hero.pack_configure(expand=True, pady=0)
        self.titulo_a.configure(font=self._fuente(46, display=True))
        self.titulo_b.configure(font=self._fuente(46, display=True))
        self.subtitulo.pack(pady=(2, 28), before=self.boton)
        self.boton.configure(
            state="normal", text="Scan", width=220, height=50, corner_radius=12
        )

        self._resultados_visibles = False
        self._decoracion = True
        self._dibujar_fondo()

    # ---- Scanning
    def iniciar_escaneo(self):
        self._escaneando = True
        self.boton.configure(state="disabled", text="Scanning...")
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
            self.estado.configure(text=f"{formatear_numero(archivos)} files scanned")
            self.after(120, self._actualizar_progreso)
        else:
            self._mostrar_resultados()

    # ---- Results
    def _mostrar_resultados(self):
        self._escaneando = False
        self.progreso.stop()
        self.progreso.pack_forget()
        self.estado.pack_forget()

        # Compact the top area and show the results panel
        self.hero.pack_configure(expand=False, pady=(18, 6))
        self.titulo_a.configure(font=self._fuente(30, display=True))
        self.titulo_b.configure(font=self._fuente(30, display=True))
        self.subtitulo.pack_forget()
        self.boton.configure(
            state="normal", text="Scan", width=170, height=40, corner_radius=10
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

        # Clear the search only if text was typed (so the placeholder
        # isn't wiped) and leave the focus on the table.
        if self.caja_busqueda.get():
            self.caja_busqueda.delete(0, "end")
        self.tabla.focus_set()

        self._actualizar_estadisticas()

        # The initial result goes from largest to smallest
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

    # ---- Search
    @staticmethod
    def _es_ampliacion(anteriores, nuevas):
        """
        True if every previous word is contained in some new word.
        In that case the new results are a subset of the previous ones
        and it is enough to filter over them.
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
                base = cache[3]    # only search within what is already filtered

            self.vista = self.indice.filtrar(base, palabras)
            self._cache_busqueda = (palabras, columna, desc, self.vista)
            self.contador.configure(text=f"{len(self.vista)} of {len(self.indice)}")
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

    # ---- Sort when clicking a column
    def ordenar_por(self, columna):
        if columna == self.orden_col:
            self.orden_desc = not self.orden_desc      # toggle
        else:
            self.orden_col = columna
            # Size and date start largest-first, name starts A to Z
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

    # ---- Virtual table: only visible rows are drawn
    def _renderizar(self):
        self._cerrar_menu()            # if the table moves, the menu no longer lines up
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

        # Keep the selection if its row is still visible
        if self._sel_pos is not None and self._inicio <= self._sel_pos < fin:
            self.tabla.selection_set(str(self.vista[self._sel_pos]))

        if total:
            self.scroll.set(self._inicio / total, fin / total)
        else:
            self.scroll.set(0, 1)

    def _desplazar(self, *args):
        """Scrollbar command."""
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

    # ---- Dropdown menu over the file name
    def _clic_tabla(self, evento):
        # Only clicks in the name column open the menu
        if self.tabla.identify_column(evento.x) != "#1":
            return
        iid = self.tabla.identify_row(evento.y)
        if not iid:
            return
        # If the menu was already open for this row, the click closes it.
        # The global click (which runs right after) closes the menu and
        # opening is done at the end, once the event has finished.
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
        # Clicks inside the menu itself: let its buttons act
        if (ruta_widget + ".").startswith(str(self._menu) + "."):
            return
        self._cerrar_menu()

    def _abrir_menu(self, iid):
        self._cerrar_menu()
        if self._overlay is not None or self.indice is None:
            return

        bbox = self.tabla.bbox(iid, "#1")
        if not bbox:                   # row not visible
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
            text="Open location",
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
            text="Delete",
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

        # Place the menu right below the name cell
        menu.update_idletasks()
        ancho = menu.winfo_reqwidth()
        alto = menu.winfo_reqheight()
        x_raiz = self.tabla.winfo_rootx() + x - self.winfo_rootx()
        y_raiz = self.tabla.winfo_rooty() + y + alto_celda - self.winfo_rooty() + 4
        x_raiz = max(8, min(x_raiz, self.winfo_width() - ancho - 8))
        if y_raiz + alto > self.winfo_height() - 8:
            # No room below: open upwards
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

    # ---- Delete dialog (modal overlay)
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
            text="Are you sure you want to delete this?",
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
            text="The file will be permanently deleted and will not go to the Recycle Bin.",
            text_color=TEXTO_SUAVE,
            font=self._fuente(14),
            wraplength=460,
            justify="left",
        ).pack(anchor="w", padx=28, pady=(0, 22))

        fila = ctk.CTkFrame(tarjeta, fg_color="transparent")
        fila.pack(fill="x", padx=28, pady=(0, 26))

        ctk.CTkButton(
            fila,
            text="Cancel",
            width=130,
            height=44,
            corner_radius=10,
            fg_color=ELEVADO,
            hover_color="#333333",
            text_color=TEXTO,
            font=self._fuente(15),
            command=self._cerrar_dialogo,
        ).pack(side="left")

        # Delete button: disabled until the countdown ends
        self._btn_borrar = ctk.CTkButton(
            fila,
            text=f"Delete ({CUENTA_ATRAS})",
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
            self._btn_borrar.configure(text=f"Delete ({self._restantes})")
            self._cuenta_id = self.after(1000, self._tick_cuenta)
        else:
            self._btn_borrar.configure(
                text="Delete",
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
            text="Deleting...",
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
        """Worker thread: deletes the file and prepares the updated index."""
        try:
            try:
                os.remove(ruta)
            except FileNotFoundError:
                self._resultado_borrado = (False, "The file no longer exists at that location.", None)
                return
            except PermissionError:
                self._resultado_borrado = (
                    False,
                    "You don't have permission to delete it, or it is open in another program.",
                    None,
                )
                return
            except OSError as e:
                self._resultado_borrado = (False, f"System error: {e.strerror or e}", None)
                return

            self._resultado_borrado = (True, "", indice.sin_ruta(ruta))
        except Exception as e:
            traceback.print_exc()
            self._resultado_borrado = (False, f"Unexpected error: {e}", None)

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
            titulo, color = "File deleted", VERDE
            detalle = (
                f"\u201c{self._nombre_borrar}\u201d was deleted successfully.\n"
                f"You freed up {formatear_tamano(self._tam_borrar)} of space."
            )
        else:
            titulo, color = "Could not delete", ROJO_CLARO
            detalle = f"\u201c{self._nombre_borrar}\u201d was not deleted.\n{msg}"

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
            text="Close",
            height=44,
            corner_radius=10,
            fg_color=ELEVADO,
            hover_color="#333333",
            text_color=TEXTO,
            font=self._fuente(15),
            command=self._cerrar_dialogo,
        ).pack(fill="x", padx=28, pady=(0, 26))


if __name__ == "__main__":
    # Register the font before creating the window
    cargar_fuente_propia(RUTA_FUENTE_PROPIA)
    SimpleCleaner().mainloop()