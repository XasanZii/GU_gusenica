import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import os
import sys
from pathlib import Path
import threading

try:
    import cv2
except ImportError:
    cv2 = None
try:
    import rawpy
except ImportError:
    rawpy = None


def resource_path(relative_path):
    """Получает правильный путь к файлам и в EXE, и в обычном Python"""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class NotificationPopup:
    """Красивое всплывающее уведомление"""
    
    def __init__(self, root, message, popup_type="info", duration=3000):
        self.root = root
        self.message = message
        self.popup_type = popup_type
        self.duration = duration
        
        self.popup = tk.Toplevel(root)
        self.popup.wm_overrideredirect(True)
        self.popup.attributes('-topmost', True)
        self.popup.attributes('-alpha', 0.95)
        
        colors = {
            "success": ("#4CAF50", "#FFFFFF"),
            "error": ("#F44336", "#FFFFFF"),
            "warning": ("#FF9800", "#FFFFFF"),
            "info": ("#2196F3", "#FFFFFF")
        }
        
        bg_color, text_color = colors.get(popup_type, colors["info"])
        
        frame = tk.Frame(self.popup, bg=bg_color)
        frame.pack(padx=15, pady=10)
        
        label = tk.Label(
            frame,
            text=message,
            bg=bg_color,
            fg=text_color,
            font=("Segoe UI", 10),
            padx=15,
            pady=10
        )
        label.pack()
        
        self.popup.update_idletasks()
        width = self.popup.winfo_width()
        height = self.popup.winfo_height()
        x = root.winfo_x() + root.winfo_width() - width - 20
        y = root.winfo_y() + 20
        
        self.popup.geometry(f"+{x}+{y}")
        self.popup.after(duration, self.close)
    
    def close(self):
        try:
            self.popup.destroy()
        except:
            pass


class ImageConverter:
    """Основной класс приложения"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Конвертер изображений")
        self.root.geometry("1000x700")
        self.root.minsize(900, 600)
        self.root.configure(bg="#1a1a1a")
        
        # Переменные
        self.current_image = None
        self.current_image_path = None
        self.quality = tk.IntVar(value=85)
        self.is_converting = False
        
        # Инициализация переменных прогресса (ИСПРАВЛЕНО)
        self.progress_bar_id = None
        
        # Фоновое изображение
        self.background_image = None
        self.background_photo = None
        self.background_id = None
        
        # Допустимые форматы
        self.formats = ["PNG", "JPG", "WEBP", "BMP", "TIFF", "ICO"]
        self.format_extensions = {
            "PNG": ".png",
            "JPG": ".jpg",
            "WEBP": ".webp",
            "BMP": ".bmp",
            "TIFF": ".tiff",
            "ICO": ".ico"
        }
        
        if rawpy is None:
            print("⚠️ Для работы с RAW форматами (NEF, CR2 и т.д.) установите: pip install rawpy")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Создание интерфейса"""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'TCombobox',
            fieldbackground='#6ec86e',
            background='#6ec86e',
            foreground='white',
            arrowcolor='white',
            relief='flat',
            borderwidth=0,
            padding=8,
            font=('Segoe UI', 11, 'bold')
        )
        style.map('TCombobox',
            fieldbackground=[('readonly', '#6ec86e'), ('active', '#5eb85e')],
            background=[('active', '#5eb85e')],
            foreground=[('readonly', 'white')]
        )
        
        self.canvas = tk.Canvas(self.root, bg="#1a1a1a", highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        
        try:
            self.background_image = Image.open(resource_path("background.jpg"))
            self._update_background()
        except:
            pass
        
        # Элементы прогресса (ИСПРАВЛЕНО: теперь они создаются)
        self.progress_label = tk.Label(self.canvas, text="", bg="#1a1a1a", fg="white", font=("Segoe UI", 10))
        self.progress_bar = tk.Canvas(self.canvas, width=200, height=4, bg="#333333", highlightthickness=0)
        self.progress_label_window = None
        self.progress_bar_window = None

        self.select_btn = tk.Button(
            self.canvas, text="📂 Выбрать изображение", command=self.select_image,
            bg="#4a9eff", fg="white", font=("Segoe UI", 12, "bold"),
            padx=30, pady=15, relief=tk.FLAT, cursor="hand2", activebackground="#3a8eef"
        )
        
        self.back_btn = tk.Button(
            self.canvas, text="← Назад", command=self.combine_buttons,
            bg="#ff6b6b", fg="white", font=("Segoe UI", 10, "bold"),
            padx=15, pady=12, relief=tk.FLAT, cursor="hand2", activebackground="#ee5a52"
        )
        
        self.format_combo = ttk.Combobox(
            self.canvas, values=self.formats, state="readonly", width=16,
            font=("Segoe UI", 11, "bold"), justify="center"
        )
        self.format_combo.current(0)
        
        self.convert_btn = tk.Button(
            self.canvas, text="✓ Конвертировать", command=self.save_image, # ИСПРАВЛЕНО: вызываем save_image для потока
            bg="#6ec86e", fg="white", font=("Segoe UI", 10, "bold"),
            padx=15, pady=12, relief=tk.FLAT, cursor="hand2", activebackground="#5eb85e"
        )
        
        self.button_window_id = None
        self.back_window_id = None
        self.format_window_id = None
        self.convert_window_id = None
        self.buttons_expanded = False
    
    def _update_background(self):
        if not self.background_image:
            return
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        if width < 1 or height < 1:
            return
        
        bg_resized = self.background_image.resize((width, height), Image.LANCZOS)
        self.background_photo = ImageTk.PhotoImage(bg_resized)
        
        if self.background_id is None:
            self.background_id = self.canvas.create_image(0, 0, anchor="nw", image=self.background_photo)
        else:
            self.canvas.itemconfig(self.background_id, image=self.background_photo)
        self.canvas.tag_lower(self.background_id)
    
    def _on_canvas_resize(self, event):
        self._update_background()
        bottom_y = event.height - 60
        
        # Перерисовка прогресс-бара при изменении размеров, если он активен
        if self.progress_label_window:
            self.canvas.coords(self.progress_label_window, event.width // 2, bottom_y - 60)
        if self.progress_bar_window:
            self.canvas.coords(self.progress_bar_window, event.width // 2, bottom_y - 45)

        if self.buttons_expanded:
            spacing = 280
            if self.back_window_id: self.canvas.delete(self.back_window_id)
            if self.format_window_id: self.canvas.delete(self.format_window_id)
            if self.convert_window_id: self.canvas.delete(self.convert_window_id)
            
            self.back_window_id = self.canvas.create_window(event.width // 2 - spacing, bottom_y, window=self.back_btn)
            self.format_window_id = self.canvas.create_window(event.width // 2, bottom_y, window=self.format_combo)
            self.convert_window_id = self.canvas.create_window(event.width // 2 + spacing, bottom_y, window=self.convert_btn)
        else:
            if self.back_window_id: self.canvas.delete(self.back_window_id)
            if self.format_window_id: self.canvas.delete(self.format_window_id)
            if self.convert_window_id: self.canvas.delete(self.convert_window_id)
            
            self.button_window_id = self.canvas.create_window(event.width // 2, bottom_y, window=self.select_btn)
    
    def select_image(self):
        file_path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Все изображения", "*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tiff *.ico *.nef *.nrw *.cr2"),
                ("PNG", "*.png"), ("JPG", "*.jpg *.jpeg"), ("WebP", "*.webp"), ("BMP", "*.bmp"),
                ("GIF", "*.gif"), ("TIFF", "*.tiff"), ("ICO", "*.ico"),
                ("Nikon RAW (NEF)", "*.nef *.nrw"), ("Canon RAW (CR2)", "*.cr2"), ("Все файлы", "*.*")
            ]
        )
        if file_path:
            self._load_image(file_path)
    
    def _load_image(self, file_path):
        try:
            if not os.path.exists(file_path):
                NotificationPopup(self.root, "Файл не найден", "error")
                return
            
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in ['.nef', '.nrw', '.cr2'] and rawpy is not None:
                try:
                    raw = rawpy.imread(file_path)
                    rgb_array = raw.postprocess()
                    image = Image.fromarray(rgb_array)
                except Exception as e:
                    NotificationPopup(self.root, f"Ошибка обработки RAW: {str(e)}", "error")
                    return
            elif file_ext in ['.nef', '.nrw', '.cr2'] and rawpy is None:
                NotificationPopup(self.root, "Установите rawpy для работы с RAW: pip install rawpy", "warning")
                return
            else:
                image = Image.open(file_path)
            
            if hasattr(image, 'format'):
                valid_formats = ['PNG', 'JPEG', 'WEBP', 'BMP', 'GIF', 'TIFF', 'ICO', 'RGB', 'RGBA']
                if image.format and image.format not in valid_formats:
                    NotificationPopup(self.root, "Неподдерживаемый формат изображения", "warning")
                    return
            
            self.current_image = image
            self.current_image_path = file_path
            
            if not self.buttons_expanded:
                self.expand_buttons()
            
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка загрузки: {str(e)}", "error")
    
    def expand_buttons(self):
        if self.buttons_expanded or not hasattr(self, 'canvas'):
            return
        self.buttons_expanded = True
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        bottom_y = height - 60
        
        if self.button_window_id:
            self.canvas.delete(self.button_window_id)
        
        self.animate_buttons_expand(width // 2, bottom_y, 0, 25)
    
    def animate_buttons_expand(self, center_x, center_y, progress, max_steps):
        if progress <= max_steps:
            ratio = progress / max_steps
            offset = (ratio * ratio) * 280
            
            if self.back_window_id: self.canvas.delete(self.back_window_id)
            if self.format_window_id: self.canvas.delete(self.format_window_id)
            if self.convert_window_id: self.canvas.delete(self.convert_window_id)
            
            self.back_window_id = self.canvas.create_window(center_x - offset, center_y, window=self.back_btn)
            self.format_window_id = self.canvas.create_window(center_x, center_y, window=self.format_combo)
            self.convert_window_id = self.canvas.create_window(center_x + offset, center_y, window=self.convert_btn)
            
            self.root.after(10, lambda: self.animate_buttons_expand(center_x, center_y, progress + 1, max_steps))
    
    def combine_buttons(self):
        if not self.buttons_expanded:
            return
        self.buttons_expanded = False
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        bottom_y = height - 60
        
        self.animate_buttons_combine(width // 2, bottom_y, 0, 25)
    
    def animate_buttons_combine(self, center_x, center_y, progress, max_steps):
        if progress <= max_steps:
            ratio = 1 - (progress / max_steps)
            offset = (ratio * ratio) * 280
            
            if self.back_window_id: self.canvas.delete(self.back_window_id)
            if self.format_window_id: self.canvas.delete(self.format_window_id)
            if self.convert_window_id: self.canvas.delete(self.convert_window_id)
            
            self.back_window_id = self.canvas.create_window(center_x - offset, center_y, window=self.back_btn)
            self.format_window_id = self.canvas.create_window(center_x, center_y, window=self.format_combo)
            self.convert_window_id = self.canvas.create_window(center_x + offset, center_y, window=self.convert_btn)
            
            self.root.after(10, lambda: self.animate_buttons_combine(center_x, center_y, progress + 1, max_steps))
        else:
            if self.back_window_id: self.canvas.delete(self.back_window_id)
            if self.format_window_id: self.canvas.delete(self.format_window_id)
            if self.convert_window_id: self.canvas.delete(self.convert_window_id)
            
            self.button_window_id = self.canvas.create_window(center_x, center_y, window=self.select_btn)
    
    def _show_progress(self, text):
        """Показать индикатор выполнения (ИСПРАВЛЕНО)"""
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        bottom_y = height - 60
        
        self.progress_label.configure(text=text, bg="#1a1a1a")
        
        if not self.progress_label_window:
            self.progress_label_window = self.canvas.create_window(width // 2, bottom_y - 60, window=self.progress_label)
        if not self.progress_bar_window:
            self.progress_bar_window = self.canvas.create_window(width // 2, bottom_y - 45, window=self.progress_bar)
            
        if self.progress_bar_id:
            self.progress_bar.delete(self.progress_bar_id)
        
        self.progress_bar_id = self.progress_bar.create_rectangle(0, 0, 100, 4, fill="#4a9eff", outline="")
    
    def _hide_progress(self):
        """Скрыть индикатор выполнения (ИСПРАВЛЕНО)"""
        self.progress_label.configure(text="")
        if self.progress_bar_id:
            self.progress_bar.delete(self.progress_bar_id)
            self.progress_bar_id = None
        if self.progress_label_window:
            self.canvas.delete(self.progress_label_window)
            self.progress_label_window = None
        if self.progress_bar_window:
            self.canvas.delete(self.progress_bar_window)
            self.progress_bar_window = None
    
    def save_image(self):
        """Сохранение изображения"""
        if not self.current_image:
            NotificationPopup(self.root, "Изображение не загружено", "warning")
            return
        
        selected_format = self.format_combo.get()
        extension = self.format_extensions[selected_format]
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=extension,
            filetypes=[(f"{selected_format} Image", f"*{extension}"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        self.is_converting = True
        thread = threading.Thread(target=self._convert_and_save, args=(file_path, selected_format))
        thread.daemon = True
        thread.start()
    
    def _convert_and_save(self, file_path, format_str):
        """Конвертация и сохранение изображения в потоке"""
        try:
            self.root.after(0, lambda: self._show_progress(f"Конвертация в {format_str}..."))
            
            image = self.current_image.copy()
            
            if format_str == "JPG":
                if image.mode in ["RGBA", "LA"] or (image.mode == "P" and "transparency" in image.info):
                    rgb_image = Image.new("RGB", image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[-1])
                    image = rgb_image
                elif image.mode != "RGB":
                    image = image.convert("RGB")
            elif format_str == "ICO":
                size = min(image.size)
                image = image.crop((0, 0, size, size))
            
            save_kwargs = {}
            if format_str in ["JPG", "WEBP"]:
                save_kwargs["quality"] = self.quality.get()
            if format_str == "PNG":
                save_kwargs["optimize"] = True
            
            # Подмена имени формата для Pillow (Pillow ожидает JPEG вместо JPG)
            save_format = "JPEG" if format_str == "JPG" else format_str
            image.save(file_path, save_format, **save_kwargs)
            
            file_size = os.path.getsize(file_path) / 1024
            
            self.root.after(0, lambda: NotificationPopup(
                self.root, f"Сохранено: {os.path.basename(file_path)} ({file_size:.1f} KB)", "success"
            ))
            self.root.after(100, self.show_gif_popup)
            
        except Exception as e:
            error_message = str(e)
            self.root.after(0, lambda: NotificationPopup(self.root, f"Ошибка сохранения: {error_message}", "error"))
        finally:
            self.root.after(0, self._hide_progress)
            self.is_converting = False
    
    def show_gif_popup(self):
        """Показать видео в центре окна после успешной конвертации"""
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
        
        gif_window = tk.Toplevel(self.root)
        gif_window.title("")
        gif_window.attributes('-topmost', True)
        gif_window.resizable(False, False)
        gif_window.configure(bg="#1a1a1a")
        gif_window.overrideredirect(True)
        
        gif_size = 400
        gif_window.geometry(f"{gif_size}x{gif_size}")
        
        gif_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (gif_size // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (gif_size // 2)
        gif_window.geometry(f"{gif_size}x{gif_size}+{x}+{y}")
        
        canvas = tk.Canvas(gif_window, bg="#1a1a1a", highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        
        self.video_frames = []
        self.video_index = 0
        
        try:
            fps = video.get(cv2.CAP_PROP_FPS)
            frame_delay = max(int(1000 / fps) if fps > 0 else 33, 20)
            
            while True:
                ret, frame = video.read()
                if not ret:
                    break
                
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                height, width = frame_rgb.shape[:2]
                aspect = width / height
                new_height = gif_size - 20
                new_width = int(new_height * aspect)
                if new_width > gif_size - 20:
                    new_width = gif_size - 20
                    new_height = int(new_width / aspect)
                
                frame_resized = cv2.resize(frame_rgb, (new_width, new_height))
                pil_frame = Image.fromarray(frame_resized)
                photo = ImageTk.PhotoImage(pil_frame)
                self.video_frames.append(photo)
            
            video.release()
            
            if not self.video_frames:
                NotificationPopup(self.root, "Видео не содержит кадров", "error")
                gif_window.destroy()
                return
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка обработки видео: {str(e)}", "error")
            gif_window.destroy()
            return
        
        video_photo_id = canvas.create_image(gif_size // 2, gif_size // 2, image=self.video_frames[0])
        
        def animate_video():
            if gif_window.winfo_exists():
                canvas.itemconfig(video_photo_id, image=self.video_frames[self.video_index])
                self.video_index = (self.video_index + 1) % len(self.video_frames)
                gif_window.after(frame_delay, animate_video)
        
        animate_video()
        
        # ИСПРАВЛЕНО: Очищаем ссылки на кадры при закрытии, чтобы освободить ОЗУ
        def on_close():
            self.video_frames = []
            if gif_window.winfo_exists():
                gif_window.destroy()

        gif_window.after(5000, on_close)
    
    def run(self):
        """Запуск приложения"""
        self.root.mainloop()


def main():
    root = tk.Tk()
    app = ImageConverter(root)
    app.run()


if __name__ == "__main__":
    main()