import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from PIL import Image, ImageTk
import os
import sys
import json
import threading
import math

try:
    import cv2
except ImportError:
    cv2 = None
try:
    import rawpy
except ImportError:
    rawpy = None
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None
try:
    import vlc
except ImportError:
    vlc = None


def resource_path(relative_path):
    """Получает правильный путь к встроенным файлам (для EXE и для разработки)."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


def app_dir():
    """Возвращает директорию, где находится исполняемый файл (или .py)."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def load_settings():
    """Загружает настройки из settings.json рядом с exe/py."""
    path = os.path.join(app_dir(), "settings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_settings(data):
    """Сохраняет настройки в settings.json рядом с exe/py."""
    path = os.path.join(app_dir(), "settings.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except:
        pass


class NotificationPopup:
    """Всплывающее уведомление — просто одноцветный прямоугольник без рамок.
    
    Плавно выезжает справа, задерживается, плавно исчезает.
    """
    
    def __init__(self, root, message, popup_type="info", duration=3000):
        self.root = root
        colors = {
            "success": ("#4CAF50", "#FFFFFF"),
            "error": ("#F44336", "#FFFFFF"),
            "warning": ("#FF9800", "#FFFFFF"),
            "info": ("#4A90D9", "#FFFFFF")
        }
        bg_color, text_color = colors.get(popup_type, colors["info"])
        
        self.popup = tk.Toplevel(root)
        self.popup.wm_overrideredirect(True)
        self.popup.attributes('-topmost', True)
        
        frame = tk.Frame(self.popup, bg=bg_color)
        frame.pack()
        
        tk.Label(frame, text=message, bg=bg_color, fg=text_color,
                 font=("Segoe UI", 10), padx=20, pady=12).pack()
        
        self.popup.update_idletasks()
        self._w = self.popup.winfo_width()
        self._h = self.popup.winfo_height()
        
        self._start_x = root.winfo_x() + root.winfo_width()
        self._start_y = root.winfo_y() + 20
        self.popup.geometry(f"+{self._start_x}+{self._start_y}")
        
        self._slide_in(duration)
    
    def _slide_in(self, duration):
        target_x = self._start_x - self._w - 10
        self._slide_step(0, 15, target_x, duration)
    
    def _slide_step(self, step, total, target_x, duration):
        if step > total:
            self.popup.after(duration, self._slide_out)
            return
        t = step / total
        ease = 1 - (1 - t) ** 3
        x = self._start_x - (self._start_x - target_x) * ease
        self.popup.geometry(f"+{int(x)}+{self._start_y}")
        self.popup.attributes('-alpha', ease * 0.95)
        self.popup.after(16, lambda: self._slide_step(step + 1, total, target_x, duration))
    
    def _slide_out(self):
        self.popup.attributes('-alpha', 1)
        self._slide_out_step(0, 10)
    
    def _slide_out_step(self, step, total):
        if step > total:
            self._close()
            return
        t = step / total
        self.popup.attributes('-alpha', 1 - t)
        self.popup.after(20, lambda: self._slide_out_step(step + 1, total))
    
    def _close(self):
        try:
            self.popup.destroy()
        except:
            pass


# Shared helpers for 3D drawing
def _arc_pts(cx1, cy1, cx2, cy2, start_angle, extent, steps=10):
    cx = (cx1 + cx2) / 2
    cy = (cy1 + cy2) / 2
    rx = (cx2 - cx1) / 2
    ry = (cy2 - cy1) / 2
    pts = []
    for i in range(steps + 1):
        a = math.radians(start_angle + extent * i / steps)
        pts.append(cx + rx * math.cos(a))
        pts.append(cy + ry * math.sin(a))
    return pts

def _draw_rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = []
    pts.extend(_arc_pts(x2 - r, y1, x2, y1 + r, 0, 90))
    pts.extend([x2, y1 + r, x2, y2 - r])
    pts.extend(_arc_pts(x2 - r, y2 - r, x2, y2, 90, 90))
    pts.extend([x2 - r, y2, x1 + r, y2])
    pts.extend(_arc_pts(x1, y2 - r, x1 + r, y2, 180, 90))
    pts.extend([x1, y2 - r, x1, y1 + r])
    pts.extend(_arc_pts(x1, y1, x1 + r, y1 + r, 270, 90))
    pts.extend([x1 + r, y1, x2 - r, y1])
    return canvas.create_polygon(pts, smooth=True, **kw)

def _lerp_color(c1, c2, t):
    if c1 == c2 or not c1 or not c2:
        return c1 if t < 0.5 else c2
    try:
        t = max(0.0, min(1.0, t))
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        return f"#{int(r1 + (r2 - r1) * t):02x}{int(g1 + (g2 - g1) * t):02x}{int(b1 + (b2 - b1) * t):02x}"
    except Exception:
        return c1 if t < 0.5 else c2

def _ease_out_back(t):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


class _3DButton(tk.Canvas):
    """Голубая 3D-кнопка с эффектом объёма."""
    
    _ANIM_DURATION = 200
    _FRAME_INTERVAL = 16
    
    N_TOP = "#5B9EF4"
    N_FACE = "#3A8BED"
    N_BOTTOM = "#1A5BBF"
    N_SHADOW = "#0F3D7A"
    N_BORDER = "#1A4D8A"
    
    H_TOP = "#7BB5FF"
    H_FACE = "#5B9EF4"
    H_BOTTOM = "#2B7DE9"
    H_SHADOW = "#1A5BBF"
    H_BORDER = "#2B5FA8"
    
    P_TOP = "#1A5BBF"
    P_FACE = "#1A5BBF"
    P_BOTTOM = "#0F3D7A"
    P_SHADOW = "#0A2A55"
    P_BORDER = "#0F2A55"
    
    D_TOP = "#808080"
    D_FACE = "#707070"
    D_BOTTOM = "#505050"
    D_SHADOW = "#404040"
    D_BORDER = "#505050"
    
    TEXT_COLOR = "#FFFFFF"
    
    def __init__(self, parent, text="", command=None, width=220, height=50,
                 border_radius=8, font=("Segoe UI", 11, "bold")):
        self._text = text.upper()
        self._command = command
        self._base_w = width
        self._h = height
        self._r = border_radius
        self._font = font
        
        pad = 4
        super().__init__(parent, highlightthickness=0, bd=0,
                         bg=parent["bg"], width=width + pad * 2, height=height + pad * 2)
        
        self._cur_top = self.N_TOP
        self._cur_face = self.N_FACE
        self._cur_bottom = self.N_BOTTOM
        self._cur_shadow = self.N_SHADOW
        self._cur_border = self.N_BORDER
        self._cur_offset = 0
        
        self._hovered = False
        self._pressed = False
        self._anim_id = None
        self._disabled = False
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        
        self._redraw()
    
    def _redraw(self):
        self.delete("all")
        pad = 4
        cw = int(self._base_w + pad * 2)
        ch = int(self._h + pad * 2)
        if cw < 4 or ch < 4:
            return
        
        offset = int(self._cur_offset)
        bx1, by1 = pad, pad + offset
        bx2, by2 = cw - pad, ch - pad + offset
        bw, bh = bx2 - bx1, by2 - by1
        
        _draw_rounded_rect(self, 0, 0, cw, ch, self._r, fill=self._cur_shadow, outline="", width=0)
        _draw_rounded_rect(self, bx1 + 2, by1 + 2, bx2 + 2, by2 + 2, self._r,
                          fill=self._cur_shadow, outline="", width=0)
        _draw_rounded_rect(self, bx1, by1 + 2, bx2, by2 + 2, self._r,
                          fill=self._cur_bottom, outline="", width=0)
        _draw_rounded_rect(self, bx1 - 2, by1, bx2 - 2, by2, self._r,
                          fill=self._cur_bottom, outline="", width=0)
        _draw_rounded_rect(self, bx1, by1, bx2, by2, self._r,
                          fill=self._cur_face, outline=self._cur_border, width=1)
        _draw_rounded_rect(self, bx1 + 2, by1 + 1, bx2 - 2, by1 + int(bh * 0.4), self._r,
                          fill=self._cur_top, outline="", width=0)
        self.create_text(cw // 2, (by1 + by2) // 2 - 1, text=self._text,
                         fill=self.TEXT_COLOR, font=self._font, anchor="center")
    
    def _cancel_anim(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None
    
    def set_disabled(self, disabled):
        """Переключает кнопку в серое (выключенное) состояние."""
        self._disabled = disabled
        if disabled:
            self._cur_top = self.D_TOP
            self._cur_face = self.D_FACE
            self._cur_bottom = self.D_BOTTOM
            self._cur_shadow = self.D_SHADOW
            self._cur_border = self.D_BORDER
            self._cur_offset = 0
        else:
            self._cur_top = self.N_TOP
            self._cur_face = self.N_FACE
            self._cur_bottom = self.N_BOTTOM
            self._cur_shadow = self.N_SHADOW
            self._cur_border = self.N_BORDER
            self._cur_offset = 0
        self._redraw()
    
    def _on_enter(self, event):
        if self._disabled:
            return
        self._cancel_anim()
        self._hovered = True
        self._start_anim(True)
    
    def _on_leave(self, event):
        if self._disabled:
            return
        self._cancel_anim()
        self._hovered = False
        self._pressed = False
        self._start_anim(False)
    
    def _on_press(self, event):
        self._cancel_anim()
        self._pressed = True
        if not self._disabled:
            self._cur_top = self.P_TOP
            self._cur_face = self.P_FACE
            self._cur_bottom = self.P_BOTTOM
            self._cur_shadow = self.P_SHADOW
            self._cur_border = self.P_BORDER
            self._cur_offset = 2
            self._redraw()
    
    def _on_release(self, event):
        self._pressed = False
        if self._command:
            self._command()
        if self._disabled:
            return
        if self._hovered:
            self._start_anim(True)
        else:
            self._start_anim(False)
    
    def _start_anim(self, forward):
        start = dict(top=self._cur_top, face=self._cur_face,
                     bottom=self._cur_bottom, shadow=self._cur_shadow,
                     border=self._cur_border, offset=self._cur_offset)
        
        if forward:
            target = dict(top=self.H_TOP, face=self.H_FACE,
                          bottom=self.H_BOTTOM, shadow=self.H_SHADOW,
                          border=self.H_BORDER, offset=-1)
        else:
            target = dict(top=self.N_TOP, face=self.N_FACE,
                          bottom=self.N_BOTTOM, shadow=self.N_SHADOW,
                          border=self.N_BORDER, offset=0)
        
        self._anim_frame = 0
        self._anim_total = self._ANIM_DURATION // self._FRAME_INTERVAL
        self._anim_start = start
        self._anim_target = target
        self._anim_step()
    
    def _anim_step(self):
        self._anim_frame += 1
        t = min(self._anim_frame / self._anim_total, 1.0)
        e = _ease_out_back(t)
        s, tg = self._anim_start, self._anim_target
        
        self._cur_top = _lerp_color(s['top'], tg['top'], e)
        self._cur_face = _lerp_color(s['face'], tg['face'], e)
        self._cur_bottom = _lerp_color(s['bottom'], tg['bottom'], e)
        self._cur_shadow = _lerp_color(s['shadow'], tg['shadow'], e)
        self._cur_border = _lerp_color(s['border'], tg['border'], e)
        self._cur_offset = s['offset'] + (tg['offset'] - s['offset']) * e
        
        self._redraw()
        
        if t >= 1.0:
            self._anim_id = None
        else:
            self._anim_id = self.after(self._FRAME_INTERVAL, self._anim_step)


class ImageConverter:
    def __init__(self, root):
        self.root = root
        self.root.title("Глупый помощник Настикс")
        self.root.geometry("1024x720")
        self.root.minsize(900, 600)
        self.root.iconbitmap(default='')
        self.root.configure(bg="#1a1a1a")
        
        self.background_image = None
        self.background_photo = None
        self.background_id = None
        self.music_player = None
        self.music_playing = False
        self.music_btn = None
        
        self.showing_converter = False
        self.image_paths = []
        self.formats = ["PNG", "JPG", "WEBP", "BMP", "TIFF", "ICO", "HEIC"]
        self.supported_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff', '.tif', '.ico', '.nef', '.nrw', '.cr2', '.heic', '.heif'}
        
        # Анимация успешной конвертации
        self._success_anim = None
        self._success_anim_after_id = None
        self._success_gif_frames = []
        self._success_gif_delays = []
        self._success_gif_index = 0
        self._success_gif_width = 0
        self._success_gif_height = 0
        
        # Загружаем сохранённый формат
        settings = load_settings()
        self.selected_format = settings.get("format", "PNG")
        
        if vlc is None:
            print("⚠️ Для работы с музыкой установите: pip install python-vlc")
        
        self.setup_ui()
        self._init_music()
    
    def _on_format_change(self, *args):
        """Сохраняет выбранный формат при каждом изменении."""
        save_settings({"format": self.format_combo.get()})
    
    def setup_ui(self):
        self.canvas = tk.Canvas(self.root, bg="#1a1a1a", highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        
        try:
            self.background_image = Image.open(resource_path("background.jpg"))
            self._update_background()
        except:
            pass

        # Главные кнопки меню
        self.schedule_btn = _3DButton(self.canvas, text="РАБОЧИЙ ГРАФИК", command=None,
                                       width=240, height=52, font=("Segoe UI", 11, "bold"))
        self.finance_btn = _3DButton(self.canvas, text="РАСЧЕТ ФИНАНСОВ", command=None,
                                      width=240, height=52, font=("Segoe UI", 11, "bold"))
        self.extra_btn = _3DButton(self.canvas, text="КОНВЕРТЕР", command=self._show_converter_buttons, 
                                    width=240, height=52, font=("Segoe UI", 11, "bold"))
        
        # Кнопки конвертера
        self.folder_btn = _3DButton(self.canvas, text="ВЫБОР ПАПКИ", command=self._select_folder,
                                     width=240, height=52, font=("Segoe UI", 11, "bold"))
        self.convert_btn = _3DButton(self.canvas, text="КОНВЕРТАЦИЯ", command=self._convert_images,
                                      width=240, height=52, font=("Segoe UI", 11, "bold"))
        self.back_btn = _3DButton(self.canvas, text="НАЗАД", command=self._show_main_buttons,
                                   width=160, height=48, font=("Segoe UI", 10, "bold"))
        
        # Выпадающий список форматов: стиль под 3D-кнопки, без выделений
        def handle_combo_change(event):
            self.format_combo.selection_clear()
            self.canvas.focus_set()
            self._on_format_change(event)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Custom.TCombobox",
                        padding=(8, 18, 8, 18),
                        fieldbackground="#3A8BED",
                        background="#3A8BED",
                        foreground="#FFFFFF",
                        arrowcolor="#FFFFFF",
                        bordercolor="#1A5BBF",
                        lightcolor="#1A5BBF",
                        darkcolor="#1A5BBF",
                        selectbackground="#3A8BED",
                        selectforeground="#FFFFFF",
                        insertcolor="#FFFFFF")
        style.map("Custom.TCombobox",
                  fieldbackground=[('readonly', '#3A8BED'),
                                   ('active', '#5B9EF4'),
                                   ('pressed', '#1A5BBF')],
                  foreground=[('readonly', '#FFFFFF'),
                              ('active', '#FFFFFF'),
                              ('pressed', '#FFFFFF')],
                  selectbackground=[('readonly', '#3A8BED'),
                                    ('active', '#3A8BED'),
                                    ('pressed', '#3A8BED')],
                  selectforeground=[('readonly', '#FFFFFF'),
                                    ('active', '#FFFFFF'),
                                    ('pressed', '#FFFFFF')],
                  bordercolor=[('focus', '#1A5BBF'), ('!focus', '#1A5BBF')])

        self.format_combo = ttk.Combobox(self.canvas, values=self.formats, state="readonly",
                                         width=25, font=("Segoe UI", 11, "bold"),
                                         style="Custom.TCombobox")
        self.format_combo.configure(height=7)
        self.format_combo.set(self.selected_format)
        self.format_combo.bind("<<ComboboxSelected>>", handle_combo_change)
        self.format_combo['postcommand'] = self._disable_combo_highlight
        
        # Кнопка музыки в правом верхнем углу
        self.music_btn = _3DButton(self.canvas, text="♫ ВКЛ", command=self._toggle_music,
                                    width=80, height=36, font=("Segoe UI", 9, "bold"))
        
        # Progressbar для отображения прогресса конвертации (вертикальный, Windows-style)
        self.progress_var = tk.DoubleVar()
        
        style = ttk.Style()
        style.theme_use('winnative')
        style.layout('Win.Vertical.TProgressbar', 
                     [('Vertical.Progressbar.trough',
                       {'sticky': 'nswe', 
                        'children': [('Vertical.Progressbar.pbar',
                                    {'side': 'bottom', 'sticky': 'we'})]}),
                      ('Vertical.Progressbar.label', {'sticky': 'nswe'})])
        style.configure('Win.Vertical.TProgressbar', 
                        background='#0066CC',
                        troughcolor='#E0E0E0',
                        bordercolor='#808080',
                        lightcolor='#E0E0E0',
                        darkcolor='#808080',
                        foreground='#FFFFFF',
                        font=('Segoe UI', 9))
        
        self.progress_bar = ttk.Progressbar(self.canvas, variable=self.progress_var,
                                            maximum=100, length=200, mode='determinate',
                                            orient='vertical',
                                            style='Win.Vertical.TProgressbar')
        self.progress_window_id = None
        
        self.music_window_id = None
        self.schedule_window_id = None
        self.finance_window_id = None
        self.extra_window_id = None
        self.folder_window_id = None
        self.format_window_id = None
        self.convert_window_id = None
        self.back_window_id = None
    
    def _select_folder(self):
        """Открывает диалог выбора папки и проверяет наличие изображений."""
        folder = filedialog.askdirectory(title="Выберите папку с изображениями")
        if not folder:
            return
        
        # Проверяем, существует ли папка
        if not os.path.isdir(folder):
            NotificationPopup(self.root, "Выбранная папка не существует", "error")
            return
        
        paths = []
        try:
            for f in os.listdir(folder):
                ext = os.path.splitext(f)[1].lower()
                if ext in self.supported_extensions:
                    paths.append(os.path.join(folder, f))
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка доступа к папке: {e}", "error")
            return
        
        if not paths:
            NotificationPopup(self.root, "В выбранной папке не найдено изображений", "warning")
            self.image_paths = []
        else:
            self.image_paths = paths
            NotificationPopup(self.root, f"Найдено {len(paths)} изображений", "success", duration=4000)

    def _open_image(self, src_path):
        """Открывает изображение с поддержкой RAW (NEF и др.) и HEIC форматов."""
        ext = os.path.splitext(src_path)[1].lower()
        
        # Попытка открыть RAW файлы через rawpy
        if ext in ('.nef', '.nrw', '.cr2', '.cr3', '.arw', '.dng'):
            if rawpy is None:
                raise ImportError("Для конвертации RAW файлов установите: pip install rawpy")
            with rawpy.imread(src_path) as raw:
                # Используем параметры по умолчанию для получения качественного изображения
                rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=False)
                img = Image.fromarray(rgb)
                return img
        
        # Для HEIC/HEIF и остальных форматов используем PIL
        return Image.open(src_path)
    
    def _convert_images(self):
        """Конвертирует выбранные изображения в формат из выпадающего списка и сохраняет в папку с суффиксом _converted."""
        if not self.image_paths:
            NotificationPopup(self.root, "Сначала выберите папку с изображениями", "warning")
            return
        
        target_format = self.format_combo.get().upper()
        if not target_format:
            NotificationPopup(self.root, "Выберите формат для конвертации", "warning")
            return
        
        # Сначала убираем прошлую анимацию, если была
        self._hide_success_animation()
        
        # Определяем расширение целевого формата
        ext_map = {
            "PNG": ".png",
            "JPG": ".jpg",
            "WEBP": ".webp",
            "BMP": ".bmp",
            "TIFF": ".tiff",
            "ICO": ".ico",
            "HEIC": ".heic"
        }
        
        target_ext = ext_map.get(target_format)
        if target_ext is None:
            NotificationPopup(self.root, f"Формат {target_format} не поддерживается", "error")
            return
        
        # Создаем выходную папку с суффиксом _converted
        if self.image_paths:
            base_dir = os.path.dirname(self.image_paths[0])
            output_dir = os.path.join(base_dir, f"{os.path.basename(base_dir)}_converted")
            os.makedirs(output_dir, exist_ok=True)
        
        # Показываем прогрессбар
        self.progress_var.set(0)
        self._show_progress()
        
        converted = 0
        errors = 0
        total = len(self.image_paths)
        
        for idx, src_path in enumerate(self.image_paths, 1):
            try:
                # Пропускаем несуществующие файлы
                if not os.path.exists(src_path):
                    errors += 1
                    self.progress_var.set((idx / total) * 100)
                    continue
                
                # Открываем изображение с поддержкой RAW и HEIC
                img = self._open_image(src_path)
                
                # Конвертируем в нужный цветовой режим для совместимости
                if target_format == "JPG":
                    if img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        if 'A' in img.getbands():
                            background.paste(img, mask=img.split()[-1])
                            img = background
                        else:
                            img = img.convert('RGB')
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    base_name = os.path.splitext(os.path.basename(src_path))[0]
                    dst_path = os.path.join(output_dir, f"{base_name}{target_ext}")
                    img.save(dst_path, "JPEG", quality=95, optimize=True)
                    converted += 1
                elif target_format == "ICO":
                    base_name = os.path.splitext(os.path.basename(src_path))[0]
                    dst_path = os.path.join(output_dir, f"{base_name}{target_ext}")
                    if img.mode in ('RGBA', 'LA'):
                        img = img.convert('RGBA')
                    elif img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    img.save(dst_path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
                    converted += 1
                elif target_format == "HEIC":
                    base_name = os.path.splitext(os.path.basename(src_path))[0]
                    dst_path = os.path.join(output_dir, f"{base_name}{target_ext}")
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    img.save(dst_path, format="HEIC")
                    converted += 1
                else:
                    base_name = os.path.splitext(os.path.basename(src_path))[0]
                    dst_path = os.path.join(output_dir, f"{base_name}{target_ext}")
                    img.save(dst_path, format=target_format)
                    converted += 1
                    
            except Exception as e:
                print(f"Ошибка конвертации {src_path}: {e}")
                errors += 1
            
            # Обновляем прогресс
            self.progress_var.set((idx / total) * 100)
            self.root.update_idletasks()
        
        # Скрываем прогрессбар
        self._hide_progress()
        
        # Показываем видео по центру, если были успешные конвертации
        if converted > 0:
            self._show_success_animation()
            NotificationPopup(self.root, f"Конвертировано: {converted} изображений", "success", duration=5000)
        if errors > 0:
            NotificationPopup(self.root, f"Ошибок: {errors}", "error", duration=5000)
    
    def _show_success_animation(self):
        """Shows a looping MP4 animation centered on screen for 4 seconds using OpenCV frames on a Toplevel Label, with Pillow + root.after timing, without black bars."""
        self._hide_success_animation()
        
        video_path = resource_path("ГуГусеница.gif.mp4")
        if not os.path.exists(video_path):
            print("DEBUG: video not found:", video_path)
            return
        if cv2 is None:
            print("DEBUG: cv2 not available")
            return
        
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print("DEBUG: cv2 failed to open video")
                cap.release()
                return
            
            # Baseline sizing: keep aspect ratio, fit within 55% width and 75% height, then increase by 1.1x without exceeding root bounds
            canvas_w = self.root.winfo_width() or 1024
            canvas_h = self.root.winfo_height() or 720
            base_max_w = int(canvas_w * 0.55)
            base_max_h = int(canvas_h * 0.75)
            max_w = int(base_max_w * 1.1)
            max_h = int(base_max_h * 1.1)
            
            ret, frame = cap.read()
            if not ret:
                print("DEBUG: failed to read first frame")
                cap.release()
                return
            
            fh, fw = frame.shape[:2]
            scale = min(max_w / max(fw, 1), max_h / max(fh, 1), 1.0)
            target_w = max(1, int(round(fw * scale)))
            target_h = max(1, int(round(fh * scale)))
            
            x = (canvas_w - target_w) // 2
            y = (canvas_h - target_h) // 2
            
            vid_win = tk.Toplevel(self.root)
            vid_win.overrideredirect(True)
            vid_win.attributes('-topmost', True)
            vid_win.configure(bg='black')
            vid_win.geometry(f"{target_w}x{target_h}+{x}+{y}")
            
            label = tk.Label(vid_win, bg='black')
            label.pack()
            
            self._success_anim = {
                'cap': cap,
                'label': label,
                'window': vid_win,
                'target_w': target_w,
                'target_h': target_h,
            }
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            delay = int(1000 / max(fps, 1)) if fps and fps > 0 else 33
            self._success_anim_after_id = self.root.after(delay, self._animate_video_frame)
            self._success_anim['hide_after_id'] = self.root.after(4000, self._hide_success_animation)
        except Exception as e:
            print("DEBUG: show animation error:", e)
    
    def _animate_video_frame(self):
        """Покадрово показывает видео через OpenCV + Pillow + root.after()."""
        data = getattr(self, '_success_anim', None)
        if not data:
            return
        
        cap = data['cap']
        label = data['label']
        target_w = data['target_w']
        target_h = data['target_h']
        
        ret, frame = cap.read()
        if not ret:
            # Зацикливаем видео
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                return
        
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(frame_rgb)
            img_pil = img_pil.resize((target_w, target_h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img_pil)
            label.configure(image=photo)
            label.image = photo
        except Exception:
            pass
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        delay = int(1000 / max(fps, 1)) if fps > 0 else 33
        self._success_anim_after_id = self.root.after(delay, self._animate_video_frame)
    
    def _hide_success_animation(self):
        """Останавливает и удаляет анимацию/видео."""
        if getattr(self, '_success_anim_after_id', None):
            try:
                self.root.after_cancel(self._success_anim_after_id)
            except Exception:
                pass
            self._success_anim_after_id = None
        
        data = getattr(self, '_success_anim', None)
        if data:
            # Отменяем запланированное скрытие
            hide_id = data.get('hide_after_id')
            if hide_id:
                try:
                    self.root.after_cancel(hide_id)
                except Exception:
                    pass
            try:
                if data.get('cap'):
                    data['cap'].release()
            except Exception:
                pass
            try:
                if data.get('window'):
                    data['window'].destroy()
            except Exception:
                pass
        self._success_anim = None

    def _show_progress(self):
        """Показывает прогрессбар справа от выпадающего списка."""
        if self.progress_window_id:
            return
        x = 310
        y = 295
        self.progress_window_id = self.canvas.create_window(x, y, window=self.progress_bar)
    
    def _hide_progress(self):
        """Скрывает прогрессбар."""
        if self.progress_window_id:
            self.canvas.delete(self.progress_window_id)
            self.progress_window_id = None
    
    def _show_converter_buttons(self):
        self.showing_converter = True
        # Скрываем прогрессбар при переключении
        self._hide_progress()
        # Скрываем анимацию успеха
        self._hide_success_animation()
        # Удаляем главные кнопки
        for wid in [self.schedule_window_id, self.finance_window_id, self.extra_window_id]:
            if wid:
                self.canvas.delete(wid)
        self.schedule_window_id = None
        self.finance_window_id = None
        self.extra_window_id = None
        # Показываем кнопки конвертера
        self._update_button_positions()
    
    def _show_main_buttons(self):
        self.showing_converter = False
        # Удаляем кнопки конвертера
        for wid in [self.folder_window_id, self.format_window_id, self.convert_window_id, self.back_window_id]:
            if wid:
                self.canvas.delete(wid)
        self.folder_window_id = None
        self.format_window_id = None
        self.convert_window_id = None
        self.back_window_id = None
        # Скрываем анимацию успеха при возврате в меню
        self._hide_success_animation()
        # Показываем главные кнопки
        self._update_button_positions()
    
    def _update_button_positions(self):
        """Обновляет позиции кнопок без привязки к событию resize."""
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if w < 1:
            w = 1024
        if h < 1:
            h = 720
        self._on_canvas_resize_impl(w, h)
    
    def _update_background(self):
        if not self.background_image:
            return
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if w < 1 or h < 1:
            return
        
        bg = self.background_image.resize((w, h), Image.LANCZOS)
        self.background_photo = ImageTk.PhotoImage(bg)
        
        if self.background_id is None:
            self.background_id = self.canvas.create_image(0, 0, anchor="nw", image=self.background_photo)
        else:
            self.canvas.itemconfig(self.background_id, image=self.background_photo)
        self.canvas.tag_lower(self.background_id)
    
    def _on_canvas_resize(self, event):
        self._update_background()
        self._on_canvas_resize_impl(event.width, event.height)
    
    def _on_canvas_resize_impl(self, width, height):
        """Внутренняя реализация размещения кнопок."""
        # Кнопка музыки всегда в правом верхнем углу
        if self.music_window_id:
            self.canvas.coords(self.music_window_id, width - 70, 30)
        else:
            self.music_window_id = self.canvas.create_window(width - 70, 30, window=self.music_btn)
        
        left_x = 140
        
        if self.showing_converter:
            # Показываем кнопки конвертера
            if self.folder_window_id:
                self.canvas.coords(self.folder_window_id, left_x, 180)
            else:
                self.folder_window_id = self.canvas.create_window(left_x, 180, window=self.folder_btn)
            
            # Выпадающий список форматов
            if self.format_window_id:
                self.canvas.coords(self.format_window_id, left_x, 260)
            else:
                self.format_window_id = self.canvas.create_window(left_x, 260, window=self.format_combo)
            
            if self.convert_window_id:
                self.canvas.coords(self.convert_window_id, left_x, 340)
            else:
                self.convert_window_id = self.canvas.create_window(left_x, 340, window=self.convert_btn)
            
            if self.back_window_id:
                self.canvas.coords(self.back_window_id, left_x, 420)
            else:
                self.back_window_id = self.canvas.create_window(left_x, 420, window=self.back_btn)
        else:
            # Показываем главные кнопки меню
            if self.schedule_window_id:
                self.canvas.coords(self.schedule_window_id, left_x, 180)
            else:
                self.schedule_window_id = self.canvas.create_window(left_x, 180, window=self.schedule_btn)
            
            if self.finance_window_id:
                self.canvas.coords(self.finance_window_id, left_x, 260)
            else:
                self.finance_window_id = self.canvas.create_window(left_x, 260, window=self.finance_btn)
            
            if self.extra_window_id:
                self.canvas.coords(self.extra_window_id, left_x, 340)
            else:
                self.extra_window_id = self.canvas.create_window(left_x, 340, window=self.extra_btn)
    
    def _disable_combo_highlight(self):
        """Убирает выделение и подчеркивание в выпадающем списке combobox."""
        try:
            lb = self.format_combo._listbox
            lb.configure(selectbackground='#3A8BED',
                         selectforeground='#FFFFFF',
                         activestyle='none')
        except Exception:
            pass

    def _init_music(self):
        """Инициализирует фоновую музыку (зацикленно)."""
        if vlc is None:
            return
        try:
            mp3_path = resource_path("dark_hourDEMONDICE.mp3")
            if not os.path.exists(mp3_path):
                print("⚠️ Файл dark_hourDEMONDICE.mp3 не найден")
                return
            self.music_player = vlc.MediaPlayer(mp3_path)
            
            # Зацикливание через событие окончания
            events = self.music_player.event_manager()
            events.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_music_end)
            
            self.music_player.play()
            self.music_playing = True
        except Exception as e:
            print(f"⚠️ Ошибка инициализации музыки: {e}")
    
    def _on_music_end(self, event):
        """Перезапускает трек при окончании."""
        if self.music_player and self.music_playing:
            self.music_player.stop()
            self.music_player.play()
    
    def _toggle_music(self):
        """Включает/выключает музыку."""
        if self.music_player is None:
            return
        if self.music_playing:
            self.music_player.pause()
            self.music_playing = False
            self.music_btn._text = "♫ ВЫКЛ"
            self.music_btn.set_disabled(True)
        else:
            self.music_player.play()
            self.music_playing = True
            self.music_btn._text = "♫ ВКЛ"
            self.music_btn.set_disabled(False)
    
    def run(self):
        self.root.mainloop()


def main():
    root = tk.Tk()
    ImageConverter(root).run()


if __name__ == "__main__":
    main()