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
        # Команда выполняется даже в сером состоянии (чтобы можно было включить музыку обратно)
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


class _3DDropdown(tk.Canvas):
    """Выпадающий список в 3D-стиле со скроллбаром."""
    
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
    
    TEXT_COLOR = "#FFFFFF"
    
    SCROLLBAR_COLOR = "#C0C8D4"
    SCROLLBAR_HOVER = "#A0AAB8"
    SCROLLBAR_BG = "#E8ECF0"
    
    MENU_BORDER = "#1A5BBF"
    MENU_BG = "#F5F9FF"
    MENU_ITEM_BG = "#FFFFFF"
    MENU_ITEM_HOVER = "#D6E8FF"
    MENU_ITEM_SELECTED = "#B3D4FF"
    MENU_TEXT = "#1A2B4A"
    MENU_TEXT_HOVER = "#0D1B33"
    MENU_SEPARATOR = "#C8D8E8"
    
    def __init__(self, parent, values=None, default=None, on_change=None,
                 width=200, height=48, font=("Segoe UI", 11, "bold"), command=None):
        self._values = values or []
        self._on_change = on_change  # callback for format changes
        self._selected = default if default and default in self._values else (values[0] if values else "")
        self._font = font
        self._command = command
        self._base_w = width
        self._h = height
        self._menu_open = False
        self._menu_window = None
        
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
        self._anim_id = None
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        
        self._redraw()
    
    def get(self):
        return self._selected
    
    def set_value(self, value):
        """Установить значение и перерисовать."""
        if value in self._values:
            self._selected = value
            self._redraw()
    
    def current(self, index):
        if 0 <= index < len(self._values):
            self._selected = self._values[index]
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
        bh = by2 - by1
        
        _draw_rounded_rect(self, 0, 0, cw, ch, 8, fill=self._cur_shadow, outline="", width=0)
        _draw_rounded_rect(self, bx1 + 2, by1 + 2, bx2 + 2, by2 + 2, 8,
                          fill=self._cur_shadow, outline="", width=0)
        _draw_rounded_rect(self, bx1, by1 + 2, bx2, by2 + 2, 8,
                          fill=self._cur_bottom, outline="", width=0)
        _draw_rounded_rect(self, bx1 - 2, by1, bx2 - 2, by2, 8,
                          fill=self._cur_bottom, outline="", width=0)
        _draw_rounded_rect(self, bx1, by1, bx2, by2, 8,
                          fill=self._cur_face, outline=self._cur_border, width=1)
        _draw_rounded_rect(self, bx1 + 2, by1 + 1, bx2 - 2, by1 + int(bh * 0.4), 8,
                          fill=self._cur_top, outline="", width=0)
        
        cy = (by1 + by2) // 2 - 1
        self.create_text(16, cy, text=self._selected or "Выберите формат",
                         fill=self.TEXT_COLOR, font=self._font, anchor="w")
        
        ax = cw - 20
        s = 6
        self.create_polygon([ax - s, cy - s // 2, ax + s, cy - s // 2, ax, cy + s // 2],
                           fill=self.TEXT_COLOR, outline="")
    
    def _cancel_anim(self):
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None
    
    def _on_enter(self, event):
        if not self._menu_open:
            self._cancel_anim()
            self._hovered = True
            self._start_anim(True)
    
    def _on_leave(self, event):
        if not self._menu_open:
            self._cancel_anim()
            self._hovered = False
            self._start_anim(False)
    
    def _on_click(self, event):
        if self._menu_open:
            self._close_menu()
        else:
            self._open_menu()
    
    def _open_menu(self):
        if not self._values:
            return
        
        self._menu_open = True
        self.update_idletasks()
        x = self.winfo_rootx() + 2
        
        item_height = 40
        total_height = len(self._values) * item_height
        max_visible = 6
        visible_count = min(len(self._values), max_visible)
        menu_height = visible_count * item_height + 4
        
        # Меню открывается вверх
        y = self.winfo_rooty() - menu_height - 4
        
        self._menu_window = tk.Toplevel(self)
        self._menu_window.wm_overrideredirect(True)
        self._menu_window.attributes('-topmost', True)
        self._menu_window.configure(bg=self.MENU_BORDER)
        
        menu_width = self._base_w + 8
        scrollbar_width = 12
        
        # Если элементов больше чем видно — добавляем скроллбар
        needs_scroll = len(self._values) > max_visible
        
        if needs_scroll:
            # Используем Canvas + Scrollbar для прокрутки
            menu_canvas = tk.Canvas(self._menu_window, bg=self.MENU_BG,
                                    highlightthickness=0, bd=0,
                                    width=menu_width - scrollbar_width - 4,
                                    height=menu_height - 4)
            scrollbar = tk.Scrollbar(self._menu_window, orient="vertical",
                                     command=menu_canvas.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            menu_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2, pady=2)
            
            scrollable_frame = tk.Frame(menu_canvas, bg=self.MENU_BG)
            scrollable_frame.bind("<Configure>",
                                  lambda e: menu_canvas.configure(scrollregion=menu_canvas.bbox("all")))
            
            menu_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw",
                                      width=menu_width - scrollbar_width - 8)
            menu_canvas.configure(yscrollcommand=scrollbar.set)
            
            # Колесо мыши для прокрутки
            def _on_mousewheel(event):
                menu_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            menu_canvas.bind_all("<MouseWheel>", _on_mousewheel)
            
            inner = scrollable_frame
        else:
            self._menu_window.geometry(f"{menu_width}x{menu_height}+{x}+{y}")
            inner = tk.Frame(self._menu_window, bg=self.MENU_BG,
                             highlightbackground=self.MENU_BORDER, highlightthickness=1,
                             relief="raised", bd=2)
            inner.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        for i, value in enumerate(self._values):
            is_sel = value == self._selected
            frame = tk.Frame(inner, bg=self.MENU_BG, cursor="hand2", height=item_height)
            frame.pack(fill=tk.X)
            frame.pack_propagate(False)
            
            lbl = tk.Label(frame,
                text=f"  {'✓  ' if is_sel else '   '}{value}",
                bg=self.MENU_ITEM_SELECTED if is_sel else self.MENU_ITEM_BG,
                fg=self.MENU_TEXT,
                font=("Segoe UI", 11, "bold" if is_sel else "normal"),
                anchor="w", padx=12, pady=8)
            lbl.pack(fill=tk.BOTH, expand=True)
            
            if i < len(self._values) - 1:
                tk.Frame(frame, bg=self.MENU_SEPARATOR, height=1).pack(fill=tk.X)
            
            def bind_item(idx, label):
                def on_enter(e):
                    if self._values[idx] != self._selected:
                        label.configure(bg=self.MENU_ITEM_HOVER, fg=self.MENU_TEXT_HOVER)
                def on_leave(e):
                    if self._values[idx] != self._selected:
                        label.configure(bg=self.MENU_ITEM_BG, fg=self.MENU_TEXT)
                def on_click(e):
                    old_val = self._selected
                    self._selected = self._values[idx]
                    # Если формат изменился — сохраняем
                    if old_val != self._selected and self._on_change:
                        self._on_change(self._selected)
                    if self._command:
                        self._command()
                    self._redraw()
                    self._close_menu()
                label.bind("<Enter>", on_enter)
                label.bind("<Leave>", on_leave)
                label.bind("<Button-1>", on_click)
                frame.bind("<Button-1>", on_click)
            
            bind_item(i, lbl)
        
        if needs_scroll:
            menu_canvas.configure(width=menu_width - scrollbar_width - 4, height=menu_height - 4)
            self._menu_window.geometry(f"{menu_width}x{menu_height}+{x}+{y}")
            self._menu_window._scroll_canvas = menu_canvas
            self._menu_window._mousewheel_binding = _on_mousewheel
        
        self._menu_window.bind("<FocusOut>", lambda e: self._close_menu())
        self._menu_window.update()
    
    def _close_menu(self):
        self._menu_open = False
        if self._menu_window:
            # Отвязываем колесо мыши, если было
            if hasattr(self._menu_window, '_mousewheel_binding'):
                try:
                    self._menu_window.unbind_all("<MouseWheel>")
                except:
                    pass
            try:
                self._menu_window.destroy()
            except:
                pass
            self._menu_window = None
        if not self._hovered:
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
        self.root.title("Конвертер приложения Alpha 0.1.1")
        self.root.geometry("1024x720")
        self.root.minsize(900, 600)
        self.root.iconbitmap(default='')
        self.root.configure(bg="#1a1a1a")
        
        self.image_paths = []
        self.quality = tk.IntVar(value=85)
        self.is_converting = False
        self.supported_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff', '.tif', '.ico', '.nef', '.nrw', '.cr2', '.heic', '.heif'}
        self.raw_extensions = {'.nef', '.nrw', '.cr2'}
        self.heic_extensions = {'.heic', '.heif'}
        
        self.progress_bar_id = None
        self.background_image = None
        self.background_photo = None
        self.background_id = None
        self.music_player = None
        self.music_playing = False
        self.music_btn = None
        
        self.formats = ["PNG", "JPG", "WEBP", "BMP", "TIFF", "ICO", "HEIC"]
        self.format_extensions = {
            "PNG": ".png", "JPG": ".jpg", "WEBP": ".webp",
            "BMP": ".bmp", "TIFF": ".tiff", "ICO": ".ico",
            "HEIC": ".heic"
        }
        
        # Загружаем сохранённый формат
        settings = load_settings()
        self._saved_format = settings.get("format", "PNG")
        
        if rawpy is None:
            print("⚠️ Для работы с RAW форматами (NEF, CR2 и т.д.) установите: pip install rawpy")
        if pillow_heif is None:
            print("⚠️ Для работы с HEIC/HEIF форматами установите: pip install pillow-heif")
        if vlc is None:
            print("⚠️ Для работы с музыкой установите: pip install python-vlc")
        
        self.setup_ui()
        self._init_music()
    
    def _on_format_change(self, new_format):
        """Сохраняет выбранный формат в settings.json при каждом изменении."""
        save_settings({"format": new_format})
    
    def setup_ui(self):
        self.canvas = tk.Canvas(self.root, bg="#1a1a1a", highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        
        try:
            self.background_image = Image.open(resource_path("background.jpg"))
            self._update_background()
        except:
            pass
        
        self.progress_label = tk.Label(self.canvas, text="", bg="#1a1a1a", fg="white", font=("Segoe UI", 11))
        self.progress_bar = tk.Canvas(self.canvas, width=400, height=20, bg="#2A2A2A", highlightthickness=0)
        self.progress_bar_window = None
        self.progress_label_window = None
        self.progress_percent_label = tk.Label(self.canvas, text="", bg="#1a1a1a", fg="#CCCCCC", font=("Segoe UI", 9))
        self.progress_percent_window = None

        self.select_btn = _3DButton(self.canvas, text="ВЫБРАТЬ ПАПКУ", command=self.select_image,
                                     width=240, height=52, font=("Segoe UI", 11, "bold"))
        self.back_btn = _3DButton(self.canvas, text="НАЗАД", command=self.combine_buttons,
                                   width=160, height=48, font=("Segoe UI", 10, "bold"))
        # Передаём сохранённый формат и callback для автосохранения
        self.format_combo = _3DDropdown(self.canvas, values=self.formats, default=self._saved_format,
                                         on_change=self._on_format_change,
                                         width=200, height=48, font=("Segoe UI", 11, "bold"))
        self.convert_btn = _3DButton(self.canvas, text="КОНВЕРТИРОВАТЬ", command=self.save_image,
                                      width=220, height=52, font=("Segoe UI", 11, "bold"))
        
        # Кнопка музыки в левом верхнем углу
        self.music_btn = _3DButton(self.canvas, text="♫ ВКЛ", command=self._toggle_music,
                                    width=80, height=36, font=("Segoe UI", 9, "bold"))
        
        self.button_window_id = None
        self.music_window_id = None
        self.back_window_id = None
        self.format_window_id = None
        self.convert_window_id = None
        self.buttons_expanded = False
    
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
        bottom_y = event.height - 60
        
        if self.progress_label_window:
            self.canvas.coords(self.progress_label_window, event.width // 2, bottom_y - 70)
        if self.progress_bar_window:
            self.canvas.coords(self.progress_bar_window, event.width // 2, bottom_y - 45)
        if self.progress_percent_window:
            self.canvas.coords(self.progress_percent_window, event.width // 2, bottom_y - 22)
        
        # Кнопка музыки всегда в левом верхнем углу
        if self.music_window_id:
            self.canvas.coords(self.music_window_id, 70, 30)
        else:
            self.music_window_id = self.canvas.create_window(70, 30, window=self.music_btn)
        
        if self.buttons_expanded:
            sp = 280
            for wid in [self.back_window_id, self.format_window_id, self.convert_window_id]:
                if wid: self.canvas.delete(wid)
            self.back_window_id = self.canvas.create_window(event.width // 2 - sp, bottom_y, window=self.back_btn)
            self.format_window_id = self.canvas.create_window(event.width // 2, bottom_y, window=self.format_combo)
            self.convert_window_id = self.canvas.create_window(event.width // 2 + sp, bottom_y, window=self.convert_btn)
        else:
            for wid in [self.back_window_id, self.format_window_id, self.convert_window_id]:
                if wid: self.canvas.delete(wid)
            self.button_window_id = self.canvas.create_window(event.width // 2, bottom_y, window=self.select_btn)
    
    def select_image(self):
        folder = filedialog.askdirectory(title="Выберите папку с изображениями")
        if not folder:
            return
        
        paths = []
        for f in os.listdir(folder):
            ext = os.path.splitext(f)[1].lower()
            if ext in self.supported_extensions:
                paths.append(os.path.join(folder, f))
        
        if not paths:
            NotificationPopup(self.root, "В выбранной папке не найдено изображений", "warning")
            return
        
        self.image_paths = paths
        NotificationPopup(self.root, f"Найдено {len(paths)} изображений. Выберите формат и нажмите Конвертировать",
                         "info", duration=4000)
        
        if not self.buttons_expanded:
            self.expand_buttons()
    
    def expand_buttons(self):
        if self.buttons_expanded:
            return
        self.buttons_expanded = True
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if self.button_window_id:
            self.canvas.delete(self.button_window_id)
        self._animate_expand(w // 2, h - 60, 0, 30)
    
    def _animate_expand(self, cx, cy, progress, max_steps):
        if progress > max_steps:
            return
        t = progress / max_steps
        ease_t = 1 + 1.70158 * (t - 1) ** 3 + 2.70158 * (t - 1) ** 2
        offset = ease_t * 280
        
        for wid in [self.back_window_id, self.format_window_id, self.convert_window_id]:
            if wid: self.canvas.delete(wid)
        self.back_window_id = self.canvas.create_window(cx - offset, cy, window=self.back_btn)
        self.format_window_id = self.canvas.create_window(cx, cy, window=self.format_combo)
        self.convert_window_id = self.canvas.create_window(cx + offset, cy, window=self.convert_btn)
        
        self.root.after(10, lambda: self._animate_expand(cx, cy, progress + 1, max_steps))
    
    def combine_buttons(self):
        if not self.buttons_expanded:
            return
        self.buttons_expanded = False
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        self._animate_combine(w // 2, h - 60, 0, 30)
    
    def _animate_combine(self, cx, cy, progress, max_steps):
        if progress > max_steps:
            for wid in [self.back_window_id, self.format_window_id, self.convert_window_id]:
                if wid: self.canvas.delete(wid)
            self.button_window_id = self.canvas.create_window(cx, cy, window=self.select_btn)
            return
        
        t = progress / max_steps
        ease_t = 1 - (1 - t) ** 3
        offset = (1 - ease_t) * 280
        
        for wid in [self.back_window_id, self.format_window_id, self.convert_window_id]:
            if wid: self.canvas.delete(wid)
        self.back_window_id = self.canvas.create_window(cx - offset, cy, window=self.back_btn)
        self.format_window_id = self.canvas.create_window(cx, cy, window=self.format_combo)
        self.convert_window_id = self.canvas.create_window(cx + offset, cy, window=self.convert_btn)
        
        self.root.after(10, lambda: self._animate_combine(cx, cy, progress + 1, max_steps))
    
    def _init_progress_windows(self):
        """Создаёт окна прогрессбара на canvas (вызывается однократно)."""
        if self.progress_bar_window is not None:
            return
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 1 or h < 1:
            return
        by = h - 60
        self.progress_label_window = self.canvas.create_window(w // 2, by - 70, window=self.progress_label)
        self.progress_bar_window = self.canvas.create_window(w // 2, by - 45, window=self.progress_bar)
        self.progress_percent_window = self.canvas.create_window(w // 2, by - 22, window=self.progress_percent_label)
        self.progress_bar_id = self.progress_bar.create_rectangle(0, 0, 0, 20, fill="#FF0000", outline="")
    
    def _show_progress(self, text):
        self._init_progress_windows()
        self.progress_label.configure(text=text)
    
    def _update_progress_bar(self, fraction):
        """Обновляет прогрессбар. fraction от 0.0 до 1.0.
        Цвет плавно переходит от красного (#FF0000) к рыжему (#FF8C00).
        """
        if self.progress_bar_id:
            self.progress_bar.delete(self.progress_bar_id)
        
        bar_width = 400
        fill_width = int(bar_width * fraction)
        if fill_width < 1 and fraction > 0:
            fill_width = 1
        
        # Градиент от красного (0%) к рыжему (100%)
        color = _lerp_color("#FF0000", "#FF8C00", fraction)
        
        self.progress_bar_id = self.progress_bar.create_rectangle(0, 0, fill_width, 20, fill=color, outline="")
        
        # Обновляем процент
        percent = int(fraction * 100)
        self.progress_percent_label.configure(text=f"{percent}%")
    
    def _hide_progress(self):
        self.progress_label.configure(text="")
        self.progress_percent_label.configure(text="")
        if self.progress_bar_id:
            self.progress_bar.delete(self.progress_bar_id)
            self.progress_bar_id = None
        if self.progress_label_window:
            self.canvas.delete(self.progress_label_window)
            self.progress_label_window = None
        if self.progress_bar_window:
            self.canvas.delete(self.progress_bar_window)
            self.progress_bar_window = None
        if self.progress_percent_window:
            self.canvas.delete(self.progress_percent_window)
            self.progress_percent_window = None
    
    def _get_unique_output_path(self, base_name, output_dir, ext):
        """Генерирует уникальный путь к файлу на основе оригинального имени.
        Если файл с таким именем уже существует, добавляет числовой суффикс.
        """
        out_path = os.path.join(output_dir, f"{base_name}{ext}")
        if not os.path.exists(out_path):
            return out_path
        
        counter = 1
        while True:
            out_path = os.path.join(output_dir, f"{base_name}_{counter}{ext}")
            if not os.path.exists(out_path):
                return out_path
            counter += 1
    
    def _convert_single_image(self, path, output_dir, fmt):
        ext = os.path.splitext(path)[1].lower()
        
        if ext in self.raw_extensions and rawpy is not None:
            raw = rawpy.imread(path)
            img = Image.fromarray(raw.postprocess())
        elif ext in self.raw_extensions:
            return None, "rawpy не установлен для RAW"
        elif ext in self.heic_extensions and pillow_heif is not None:
            heif_file = pillow_heif.open_heif(path)
            img = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data)
        elif ext in self.heic_extensions:
            return None, "pillow_heif не установлен для HEIC/HEIF"
        else:
            img = Image.open(path)
        
        if fmt == "JPG":
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
        elif fmt == "ICO":
            s = min(img.size)
            img = img.crop((0, 0, s, s))
        
        kwargs = {}
        if fmt in ("JPG", "WEBP"):
            kwargs["quality"] = self.quality.get()
        if fmt == "PNG":
            kwargs["optimize"] = True
        
        if fmt == "HEIC" and pillow_heif is None:
            return None, "pillow_heif не установлен для сохранения в HEIC"
        
        save_fmt = "JPEG" if fmt == "JPG" else fmt
        out_ext = self.format_extensions[fmt]
        
        # Используем оригинальное имя файла (без расширения)
        base_name = os.path.splitext(os.path.basename(path))[0]
        out = self._get_unique_output_path(base_name, output_dir, out_ext)
        
        img.save(out, save_fmt, **kwargs)
        return out, None
    
    def save_image(self):
        if not self.image_paths:
            NotificationPopup(self.root, "Сначала выберите папку с изображениями", "warning")
            return
        
        fmt = self.format_combo.get()
        src = os.path.dirname(self.image_paths[0])
        out_dir = os.path.join(os.path.dirname(src), f"{os.path.basename(src)}_converted")
        
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            NotificationPopup(self.root, f"Не удалось создать папку: {str(e)}", "error")
            return
        
        self.is_converting = True
        t = threading.Thread(target=self._batch_convert, args=(out_dir, fmt))
        t.daemon = True
        t.start()
    
    def _batch_convert(self, out_dir, fmt):
        errors = []
        success = 0
        total = len(self.image_paths)
        
        try:
            for i, path in enumerate(self.image_paths):
                if not self.is_converting:
                    break
                
                name = os.path.basename(path)
                self.root.after(0, lambda n=name, idx=i, ttl=total, f=fmt: self._show_progress(f"[{idx+1}/{ttl}] Конвертация {n} -> {f}"))
                
                _, err = self._convert_single_image(path, out_dir, fmt)
                if err:
                    errors.append(f"{name}: {err}")
                else:
                    success += 1
                
                fraction = (i + 1) / total
                self.root.after(0, lambda f=fraction: self._update_progress_bar(f))
            
            if errors:
                msg = "\n".join(errors[:5])
                if len(errors) > 5:
                    msg += f"\n... и ещё {len(errors) - 5} ошибок"
                self.root.after(0, lambda: NotificationPopup(self.root,
                    f"Готово! Успешно: {success}/{total}. Ошибок: {len(errors)}",
                    "warning" if success > 0 else "error", duration=5000))
            else:
                self.root.after(0, lambda: NotificationPopup(self.root,
                    f"✅ Все {success} изображений конвертированы в {fmt}!", "success", duration=5000))
                self.root.after(100, self.show_gif_popup)
        except Exception as e:
            self.root.after(0, lambda: NotificationPopup(self.root, f"Критическая ошибка: {str(e)}", "error"))
        finally:
            self.root.after(0, self._hide_progress)
            self.is_converting = False
    
    def show_gif_popup(self):
        if cv2 is None:
            NotificationPopup(self.root, "OpenCV не установлен. Установите: pip install opencv-python", "error")
            return
        
        try:
            video = cv2.VideoCapture(resource_path("ГуГусеница.gif.mp4"))
            if not video.isOpened():
                NotificationPopup(self.root, "Не удалось открыть видеофайл", "error")
                return
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка загрузки видео: {str(e)}", "error")
            return
        
        win = tk.Toplevel(self.root)
        win.title("")
        win.attributes('-topmost', True)
        win.resizable(False, False)
        win.configure(bg="#1a1a1a")
        win.overrideredirect(True)
        
        size = 400
        win.geometry(f"{size}x{size}")
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - size) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - size) // 2
        win.geometry(f"{size}x{size}+{x}+{y}")
        
        canvas = tk.Canvas(win, bg="#1a1a1a", highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        
        frames = []
        idx = 0
        
        try:
            fps = video.get(cv2.CAP_PROP_FPS)
            delay = max(int(1000 / fps) if fps > 0 else 33, 20)
            
            while True:
                ret, frame = video.read()
                if not ret:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                aspect = w / h
                nh = size - 20
                nw = int(nh * aspect)
                if nw > size - 20:
                    nw = size - 20
                    nh = int(nw / aspect)
                resized = cv2.resize(rgb, (nw, nh))
                frames.append(ImageTk.PhotoImage(Image.fromarray(resized)))
            
            video.release()
            if not frames:
                NotificationPopup(self.root, "Видео не содержит кадров", "error")
                win.destroy()
                return
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка обработки видео: {str(e)}", "error")
            win.destroy()
            return
        
        photo_id = canvas.create_image(size // 2, size // 2, image=frames[0])
        
        def animate():
            nonlocal idx
            if win.winfo_exists():
                canvas.itemconfig(photo_id, image=frames[idx])
                idx = (idx + 1) % len(frames)
                win.after(delay, animate)
        
        animate()
        win.after(5000, lambda: [frames.clear(), win.destroy() if win.winfo_exists() else None])
    
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