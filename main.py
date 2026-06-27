import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import font as tkfont
from tkinter import ttk
from PIL import Image, ImageTk, ImageDraw
import os
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
        
        # Цвета в зависимости от типа
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
        
        # Позиция в верхнем правом углу
        self.popup.update_idletasks()
        width = self.popup.winfo_width()
        height = self.popup.winfo_height()
        x = root.winfo_x() + root.winfo_width() - width - 20
        y = root.winfo_y() + 20
        
        self.popup.geometry(f"+{x}+{y}")
        
        # Автозакрытие
        self.popup.after(duration, self.close)
    
    def close(self):
        try:
            self.popup.destroy()
        except:
            pass


class RoundedButton:
    """Кнопка с округленными углами на Canvas"""
    
    def __init__(self, canvas, x, y, width, height, text, command, bg_color="#2196F3", hover_color="#1976D2"):
        self.canvas = canvas
        self.command = command
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text = text
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.current_color = bg_color
        self.radius = 8
        
        self.items = []
        self.create_button()
    
    def create_button(self):
        x1 = self.x - self.width // 2
        y1 = self.y - self.height // 2
        x2 = self.x + self.width // 2
        y2 = self.y + self.height // 2
        
        # Рисуем скругленный прямоугольник
        self.rect_id = self.canvas.create_polygon(
            self._rounded_rect(x1, y1, x2, y2, self.radius),
            fill=self.current_color,
            outline="",
            smooth=True
        )
        
        self.text_id = self.canvas.create_text(
            self.x, self.y,
            text=self.text,
            fill="white",
            font=("Segoe UI", 10, "bold")
        )
        
        self.items = [self.rect_id, self.text_id]
        
        for item in self.items:
            self.canvas.tag_bind(item, "<Enter>", self._on_enter)
            self.canvas.tag_bind(item, "<Leave>", self._on_leave)
            self.canvas.tag_bind(item, "<Button-1>", self._on_click)
    
    def _rounded_rect(self, x1, y1, x2, y2, radius):
        return [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1
        ]
    
    def _on_enter(self, event):
        self.canvas.itemconfig(self.rect_id, fill=self.hover_color)
    
    def _on_leave(self, event):
        self.canvas.itemconfig(self.rect_id, fill=self.bg_color)
    
    def _on_click(self, event):
        self.command()


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
        self.current_format = tk.StringVar(value="PNG")
        self.quality = tk.IntVar(value=85)
        self.is_converting = False
        
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
        
        # Проверка зависимостей
        if rawpy is None:
            print("⚠️ Для работы с RAW форматами (NEF, CR2 и т.д.) установите:")
            print("   pip install rawpy")
        
        self.setup_ui()
    
    def setup_ui(self):
        """Создание интерфейса"""
        
        # Стилизация ttk элементов
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
        
        # Главный Canvas для фона
        self.canvas = tk.Canvas(
            self.root,
            bg="#1a1a1a",
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        
        # Загрузка и отображение фонового изображения
        try:
            self.background_image = Image.open("background.jpg")
            self._update_background()
        except:
            pass
        
        # Кнопка выбора изображения на Canvas
        self.select_btn = tk.Button(
            self.canvas,
            text="📂 Выбрать изображение",
            command=self.select_image,
            bg="#4a9eff",
            fg="white",
            font=("Segoe UI", 12, "bold"),
            padx=30,
            pady=15,
            relief=tk.FLAT,
            cursor="hand2",
            activebackground="#3a8eef"
        )
        self.button_window_id = None
        
        # Левая кнопка - Назад
        self.back_btn = tk.Button(
            self.canvas,
            text="← Назад",
            command=self.combine_buttons,
            bg="#ff6b6b",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=12,
            relief=tk.FLAT,
            cursor="hand2",
            activebackground="#ee5a52"
        )
        
        # Центр - выпадающий список форматов
        self.format_combo = ttk.Combobox(
            self.canvas,
            values=self.formats,
            state="readonly",
            width=16,
            font=("Segoe UI", 11, "bold"),
            justify="center"
        )
        self.format_combo.current(0)  # PNG по умолчанию
        
        # Правая кнопка - Конвертировать
        self.convert_btn = tk.Button(
            self.canvas,
            text="✓ Конвертировать",
            command=self.convert_image,
            bg="#6ec86e",
            fg="white",
            font=("Segoe UI", 10, "bold"),
            padx=15,
            pady=12,
            relief=tk.FLAT,
            cursor="hand2",
            activebackground="#5eb85e"
        )
        
        self.button_window_id = None
        self.back_window_id = None
        self.format_window_id = None
        self.convert_window_id = None
        self.buttons_expanded = False
    
    def _update_background(self):
        """Обновление фонового изображения при изменении размера окна"""
        if not self.background_image:
            return
        
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        
        if width < 1 or height < 1:
            return
        
        # Масштабирование фона
        bg_resized = self.background_image.resize((width, height), Image.LANCZOS)
        self.background_photo = ImageTk.PhotoImage(bg_resized)
        
        if self.background_id is None:
            self.background_id = self.canvas.create_image(
                0, 0, anchor="nw", image=self.background_photo
            )
        else:
            self.canvas.itemconfig(self.background_id, image=self.background_photo)
        
        self.canvas.tag_lower(self.background_id)
    
    def _on_canvas_resize(self, event):
        """Обработка изменения размера окна"""
        self._update_background()
        
        bottom_y = event.height - 60
        
        # Если кнопки развёрнуты
        if self.buttons_expanded:
            spacing = 280
            
            if self.back_window_id:
                self.canvas.delete(self.back_window_id)
            if self.format_window_id:
                self.canvas.delete(self.format_window_id)
            if self.convert_window_id:
                self.canvas.delete(self.convert_window_id)
            
            # Левая кнопка
            self.back_window_id = self.canvas.create_window(
                event.width // 2 - spacing,
                bottom_y,
                window=self.back_btn
            )
            
            # Центральный список
            self.format_window_id = self.canvas.create_window(
                event.width // 2,
                bottom_y,
                window=self.format_combo
            )
            
            # Правая кнопка
            self.convert_window_id = self.canvas.create_window(
                event.width // 2 + spacing,
                bottom_y,
                window=self.convert_btn
            )
        else:
            # Кнопки сворачиваны - скроем все и покажем основную кнопку
            if self.back_window_id:
                self.canvas.delete(self.back_window_id)
            if self.format_window_id:
                self.canvas.delete(self.format_window_id)
            if self.convert_window_id:
                self.canvas.delete(self.convert_window_id)
            
            self.button_window_id = self.canvas.create_window(
                event.width // 2,
                bottom_y,
                window=self.select_btn
            )
    
    def select_image(self):
        """Выбор изображения"""
        file_path = filedialog.askopenfilename(
            title="Выберите изображение",
            filetypes=[
                ("Все изображения", "*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tiff *.ico *.nef *.nrw *.cr2"),
                ("PNG", "*.png"),
                ("JPG", "*.jpg *.jpeg"),
                ("WebP", "*.webp"),
                ("BMP", "*.bmp"),
                ("GIF", "*.gif"),
                ("TIFF", "*.tiff"),
                ("ICO", "*.ico"),
                ("Nikon RAW (NEF)", "*.nef *.nrw"),
                ("Canon RAW (CR2)", "*.cr2"),
                ("Все файлы", "*.*")
            ]
        )
        
        if file_path:
            self._load_image(file_path)
    
    def _load_image(self, file_path):
        """Загрузка изображения"""
        try:
            # Проверка существования файла
            if not os.path.exists(file_path):
                NotificationPopup(self.root, "Файл не найден", "error")
                return
            
            file_ext = os.path.splitext(file_path)[1].lower()
            
            # Обработка RAW форматов
            if file_ext in ['.nef', '.nrw', '.cr2'] and rawpy is not None:
                try:
                    raw = rawpy.imread(file_path)
                    # Получение RGB из RAW в полном разрешении
                    rgb_array = raw.postprocess()
                    image = Image.fromarray(rgb_array)
                except Exception as e:
                    NotificationPopup(self.root, f"Ошибка обработки RAW: {str(e)}", "error")
                    return
            elif file_ext in ['.nef', '.nrw', '.cr2'] and rawpy is None:
                NotificationPopup(self.root, "Установите rawpy для работы с RAW: pip install rawpy", "warning")
                return
            else:
                # Открытие обычных форматов
                image = Image.open(file_path)
            
            # Проверка формата
            if hasattr(image, 'format'):
                valid_formats = ['PNG', 'JPEG', 'WEBP', 'BMP', 'GIF', 'TIFF', 'ICO', 'RGB']
                if image.format and image.format not in valid_formats:
                    NotificationPopup(self.root, "Неподдерживаемый формат изображения", "warning")
                    return
            
            self.current_image = image
            self.current_image_path = file_path
            
            # Обновление информации о файле
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path) / 1024  # KB
            
            # Развернуть кнопки
            if not self.buttons_expanded:
                self.expand_buttons()
            
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка загрузки: {str(e)}", "error")
    
    def _on_format_change(self, value):
        """Изменение формата"""
        pass
    
    def expand_buttons(self):
        """Развернуть кнопки при загрузке изображения"""
        if self.buttons_expanded or not hasattr(self, 'canvas'):
            return
        
        self.buttons_expanded = True
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        bottom_y = height - 60
        
        # Скрыть основную кнопку
        if self.button_window_id:
            self.canvas.delete(self.button_window_id)
        
        # Плавное разворачивание кнопок
        self.animate_buttons_expand(
            center_x=width // 2,
            center_y=bottom_y,
            progress=0,
            max_steps=50
        )
    
    def animate_buttons_expand(self, center_x, center_y, progress, max_steps):
        """Анимация развёртывания кнопок"""
        if progress <= max_steps:
            # Вычисляем смещение с ускорением
            ratio = progress / max_steps
            offset = (ratio * ratio) * 280  # Квадратичная функция для плавности
            
            # Удаляем старые кнопки
            if self.back_window_id:
                self.canvas.delete(self.back_window_id)
            if self.format_window_id:
                self.canvas.delete(self.format_window_id)
            if self.convert_window_id:
                self.canvas.delete(self.convert_window_id)
            
            # Размещаем новые
            self.back_window_id = self.canvas.create_window(
                center_x - offset,
                center_y,
                window=self.back_btn
            )
            
            self.format_window_id = self.canvas.create_window(
                center_x,
                center_y,
                window=self.format_combo
            )
            
            self.convert_window_id = self.canvas.create_window(
                center_x + offset,
                center_y,
                window=self.convert_btn
            )
            
            # Следующий кадр
            self.root.after(10, lambda: self.animate_buttons_expand(
                center_x, center_y, progress + 1, max_steps
            ))
    
    def combine_buttons(self):
        """Объединить кнопки обратно"""
        if not self.buttons_expanded:
            return
        
        self.buttons_expanded = False
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        bottom_y = height - 60
        
        # Плавное сворачивание кнопок
        self.animate_buttons_combine(
            center_x=width // 2,
            center_y=bottom_y,
            progress=0,
            max_steps=50
        )
    
    def animate_buttons_combine(self, center_x, center_y, progress, max_steps):
        """Анимация сворачивания кнопок"""
        if progress <= max_steps:
            # Обратная квадратичная функция для плавности
            ratio = 1 - (progress / max_steps)
            offset = (ratio * ratio) * 280
            
            # Удаляем старые кнопки
            if self.back_window_id:
                self.canvas.delete(self.back_window_id)
            if self.format_window_id:
                self.canvas.delete(self.format_window_id)
            if self.convert_window_id:
                self.canvas.delete(self.convert_window_id)
            
            # Размещаем с уменьшающимся смещением
            self.back_window_id = self.canvas.create_window(
                center_x - offset,
                center_y,
                window=self.back_btn
            )
            
            self.format_window_id = self.canvas.create_window(
                center_x,
                center_y,
                window=self.format_combo
            )
            
            self.convert_window_id = self.canvas.create_window(
                center_x + offset,
                center_y,
                window=self.convert_btn
            )
            
            # Следующий кадр
            self.root.after(10, lambda: self.animate_buttons_combine(
                center_x, center_y, progress + 1, max_steps
            ))
        else:
            # После сворачивания вернуть основную кнопку
            if self.back_window_id:
                self.canvas.delete(self.back_window_id)
            if self.format_window_id:
                self.canvas.delete(self.format_window_id)
            if self.convert_window_id:
                self.canvas.delete(self.convert_window_id)
            
            self.button_window_id = self.canvas.create_window(
                center_x,
                center_y,
                window=self.select_btn
            )
    
    def _on_quality_change(self, value):
        """Изменение качества"""
        self.quality_label.configure(text=f"{value}%")
    
    def _show_progress(self, text):
        """Показать индикатор выполнения"""
        self.progress_label.configure(text=text)
        
        # Анимированный индикатор
        if self.progress_bar_id:
            self.progress_bar.delete(self.progress_bar_id)
        
        width = self.progress_bar.winfo_width()
        if width > 1:
            self.progress_bar_id = self.progress_bar.create_rectangle(
                0, 0, width * 0.5, 4, fill="#4a9eff", outline=""
            )
    
    def _hide_progress(self):
        """Скрыть индикатор выполнения"""
        self.progress_label.configure(text="")
        if self.progress_bar_id:
            self.progress_bar.delete(self.progress_bar_id)
            self.progress_bar_id = None
    
    def save_image(self):
        """Сохранение изображения"""
        if not self.current_image:
            NotificationPopup(self.root, "Изображение не загружено", "warning")
            return
        
        selected_format = self.current_format.get()
        extension = self.format_extensions[selected_format]
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=extension,
            filetypes=[
                (f"{selected_format} Image", f"*{extension}"),
                ("All Files", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        # Запуск сохранения в отдельном потоке
        self.is_converting = True
        thread = threading.Thread(
            target=self._convert_and_save,
            args=(file_path, selected_format)
        )
        thread.daemon = True
        thread.start()
    
    def _convert_and_save(self, file_path, format_str):
        """Конвертация и сохранение изображения"""
        try:
            self.root.after(0, lambda: self._show_progress(f"Конвертация в {format_str}..."))
            
            image = self.current_image.copy()
            
            # Конвертация RGBA -> RGB для JPG
            if format_str == "JPG" and image.mode == "RGBA":
                # Создание белого фона
                rgb_image = Image.new("RGB", image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[3])
                image = rgb_image
            elif format_str == "JPG" and image.mode != "RGB":
                image = image.convert("RGB")
            
            # Параметры сохранения
            save_kwargs = {}
            if format_str in ["JPG", "WEBP"]:
                save_kwargs["quality"] = self.quality.get()
            
            if format_str == "PNG":
                save_kwargs["optimize"] = True
            
            # Сохранение
            image.save(file_path, format_str, **save_kwargs)
            
            file_size = os.path.getsize(file_path) / 1024
            
            self.root.after(
                0,
                lambda: NotificationPopup(
                    self.root,
                    f"Сохранено: {os.path.basename(file_path)} ({file_size:.1f} KB)",
                    "success"
                )
            )
            
        except Exception as e:
            error_message = str(e)
            self.root.after(
                0,
                lambda msg=error_message: NotificationPopup(
                    self.root,
                    f"Ошибка сохранения: {msg}",
                    "error"
                )
            )
        
        finally:
            self.root.after(0, self._hide_progress)
            self.is_converting = False
    
    def convert_image(self):
        """Конвертировать изображение в выбранный формат"""
        if not self.current_image:
            NotificationPopup(self.root, "Нет выбранного изображения", "warning")
            return
        
        selected_format = self.format_combo.get()
        file_extension = self.format_extensions.get(selected_format, ".png")
        
        # Диалог сохранения
        file_path = filedialog.asksaveasfilename(
            defaultextension=file_extension,
            filetypes=[(f"{selected_format} файл", f"*{file_extension}"), ("Все файлы", "*.*")]
        )
        
        if not file_path:
            return
        
        try:
            # Подготовка изображения
            if selected_format == "JPG":
                # JPG не поддерживает прозрачность
                rgb_image = Image.new("RGB", self.current_image.size, (255, 255, 255))
                if self.current_image.mode == "RGBA":
                    rgb_image.paste(self.current_image, mask=self.current_image.split()[3])
                else:
                    rgb_image.paste(self.current_image)
                rgb_image.save(file_path, "JPEG", quality=85)
            elif selected_format == "ICO":
                # ICO требует квадратное изображение
                size = min(self.current_image.size)
                ico_image = self.current_image.crop((0, 0, size, size))
                ico_image.save(file_path, "ICO")
            else:
                self.current_image.save(file_path, selected_format)
            
            self.show_gif_popup()
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка: {str(e)}", "error")
    
    def show_gif_popup(self):
        """Показать видео в центре окна после успешной конвертации"""
        if cv2 is None:
            NotificationPopup(self.root, "OpenCV не установлен. Установите: pip install opencv-python", "error")
            return
        
        try:
            # Загрузка видео
            video = cv2.VideoCapture("ГуГусеница.gif.mp4")
            if not video.isOpened():
                NotificationPopup(self.root, "Не удалось открыть видеофайл", "error")
                return
        except Exception as e:
            NotificationPopup(self.root, f"Ошибка загрузки видео: {str(e)}", "error")
            return
        
        # Создание всплывающего окна
        gif_window = tk.Toplevel(self.root)
        gif_window.title("")
        gif_window.attributes('-topmost', True)
        gif_window.resizable(False, False)
        gif_window.configure(bg="#1a1a1a")
        
        # Удаление границ
        gif_window.overrideredirect(True)
        
        # Размер окна
        gif_size = 400
        gif_window.geometry(f"{gif_size}x{gif_size}")
        
        # Центрирование окна
        gif_window.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (gif_size // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (gif_size // 2)
        gif_window.geometry(f"{gif_size}x{gif_size}+{x}+{y}")
        
        # Создание канвас для видео
        canvas = tk.Canvas(gif_window, bg="#1a1a1a", highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        
        # Переменные для видео
        self.video_frames = []
        self.video_index = 0
        self.video_photo = None
        
        try:
            # Загрузка кадров из видео
            fps = video.get(cv2.CAP_PROP_FPS)
            frame_delay = max(int(1000 / fps) if fps > 0 else 33, 20)
            
            while True:
                ret, frame = video.read()
                if not ret:
                    break
                
                # Конвертирование BGR -> RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Изменение размера
                height, width = frame_rgb.shape[:2]
                aspect = width / height
                new_height = gif_size - 20
                new_width = int(new_height * aspect)
                if new_width > gif_size - 20:
                    new_width = gif_size - 20
                    new_height = int(new_width / aspect)
                
                frame_resized = cv2.resize(frame_rgb, (new_width, new_height))
                
                # Конвертирование в PIL Image
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
        
        # Начальный кадр
        self.video_photo = canvas.create_image(
            gif_size // 2, gif_size // 2,
            image=self.video_frames[0]
        )
        
        # Функция для анимации
        def animate_video():
            if gif_window.winfo_exists():
                canvas.itemconfig(self.video_photo, image=self.video_frames[self.video_index])
                self.video_index = (self.video_index + 1) % len(self.video_frames)
                gif_window.after(frame_delay, animate_video)
        
        # Запуск анимации
        animate_video()
        
        # Закрытие окна через 5 секунд
        gif_window.after(5000, lambda: gif_window.destroy() if gif_window.winfo_exists() else None)
    
    def run(self):
        """Запуск приложения"""
        self.root.mainloop()


def main():
    root = tk.Tk()
    app = ImageConverter(root)
    app.run()


if __name__ == "__main__":
    main()