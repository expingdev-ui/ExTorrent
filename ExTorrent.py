import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import urllib.parse

import customtkinter as ctk
import libtorrent as lt
import requests

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

DEFAULT_SAVE_DIR = os.path.abspath("downloads")


class TorrentApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ExTorrent — P2P Media Hub")
        self.geometry("750x720")
        self.resizable(False, False)

        self.ses = lt.session()
        self.handle = None
        self.is_downloading = False
        self.should_stop = False  
        self.is_paused = False    
        
        self.save_dir = DEFAULT_SAVE_DIR
        os.makedirs(self.save_dir, exist_ok=True)

        self.progress = 0.0
        self.status_text = "Статус: ожидание"
        self.error = None

        ctk.CTkLabel(self, text="ExTorrent Media Hub",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=10)

        self.search_frame = ctk.CTkFrame(self)
        self.search_frame.pack(pady=5, fill="x", padx=20)

        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Поиск фильмов, игр, софта...", width=520)
        self.search_entry.pack(side="left", padx=10, pady=10)
        self.search_entry.bind("<Return>", lambda event: self.start_search_thread())

        self.search_btn = ctk.CTkButton(self.search_frame, text="Найти", command=self.start_search_thread, width=100)
        self.search_btn.pack(side="left", padx=5)

        self.results_box = ctk.CTkTextbox(self, width=710, height=140)
        self.results_box.pack(pady=5, padx=20)
        self.results_box.insert("0.0", "Результаты поиска появятся здесь.\n")

        self.magnet_entry = ctk.CTkEntry(self, width=710,
                                       placeholder_text="Вставьте magnet:?xt=urn:btih:... или скопируйте из поиска выше")
        self.magnet_entry.pack(pady=5, padx=20)

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=5)

        self.magnet_btn = ctk.CTkButton(self.btn_frame, text="Скачать по magnet",
                                        command=self.download_magnet, fg_color="green")
        self.magnet_btn.pack(side="left", padx=10)

        self.select_btn = ctk.CTkButton(self.btn_frame, text="Выбрать .torrent файл",
                                        command=self.select_torrent)
        self.select_btn.pack(side="left", padx=10)

        self.control_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.control_frame.pack(pady=5)

        self.pause_btn = ctk.CTkButton(self.control_frame, text="⏸ Пауза",
                                       command=self.pause_download, state="disabled", fg_color="orange")
        self.pause_btn.pack(side="left", padx=5)

        self.stop_btn = ctk.CTkButton(self.control_frame, text="⏹ Остановить",
                                      command=self.stop_download, state="disabled", fg_color="red")
        self.stop_btn.pack(side="left", padx=5)

        self.file_label = ctk.CTkLabel(self, text="Файл не выбран", text_color="gray")
        self.file_label.pack(pady=2)

        self.dir_frame = ctk.CTkFrame(self)
        self.dir_frame.pack(pady=10, fill="x", padx=20)

        self.dir_btn = ctk.CTkButton(self.dir_frame, text="📁 Папка сохранения",
                                     command=self.select_save_dir, fg_color="gray30", width=150)
        self.dir_btn.pack(side="left", padx=5)

        self.dir_label = ctk.CTkLabel(self.dir_frame, text=self.save_dir, text_color="gray",
                                      wraplength=550, font=ctk.CTkFont(size=11))
        self.dir_label.pack(side="left", padx=10, fill="x", expand=True)

        self.progress_bar = ctk.CTkProgressBar(self, width=710)
        self.progress_bar.set(0)
        self.progress_bar.pack(pady=10)

        self.status_label = ctk.CTkLabel(self, text=self.status_text,
                                       font=ctk.CTkFont(size=13), justify="center")
        self.status_label.pack(pady=5)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.refresh_ui()


    def pause_download(self):
        """Пауза/возобновление загрузки"""
        if not self.handle:
            return

        if self.is_paused:
            self.handle.resume()
            self.is_paused = False
            self.pause_btn.configure(text="⏸ Пауза")
            print("✅ Загрузка возобновлена")
        else:
            self.handle.pause()
            self.is_paused = True
            self.pause_btn.configure(text="▶ Возобновить")
            self.status_text = "⏸ Пауза"
            print("⏸ Загрузка на паузе")

    def stop_download(self):
        """Остановка загрузки и удаление торрента"""
        if not self.handle:
            return

        response = messagebox.askyesno(
            "Подтверждение",
            "Вы уверены, что хотите остановить загрузку?\nТоррент будет удалён из очереди."
        )

        if response:
            self.should_stop = True
            self.is_downloading = False
            
            try:
                self.ses.remove_torrent(self.handle)
                self.handle = None
                print("⏹ Загрузка остановлена")
            except Exception as e:
                print(f"Ошибка при остановке: {e}")

            self.progress = 0.0
            self.status_text = "Загрузка отменена"
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")
            self.magnet_entry.delete(0, "end")


    def select_save_dir(self):
        """Открывает диалог выбора папки"""
        path = filedialog.askdirectory(
            initialdir=self.save_dir,
            title="Выберите папку для скачивания файлов"
        )
        if path:
            self.save_dir = os.path.abspath(path)
            self.dir_label.configure(text=self.save_dir)
            print(f"✅ Папка сохранения изменена на: {self.save_dir}")


    def is_cyrillic(self, text):
        """Проверяет, содержит ли текст кириллицу"""
        return any('\u0400' <= char <= '\u04FF' for char in text)

    def smart_transliterate(self, text):
        """
        Интеллектуальная транслитерация.
        Использует маппинг кириллицы на латиницу с учётом звучания.
        """
        cyrillic_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
            'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
            'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
            'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
            'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch',
            'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
            'э': 'e', 'ю': 'yu', 'я': 'ya',
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D',
            'Е': 'E', 'Ё': 'Yo', 'Ж': 'Zh', 'З': 'Z', 'И': 'I',
            'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M', 'Н': 'N',
            'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T',
            'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch',
            'Ш': 'Sh', 'Щ': 'Sch', 'Ъ': '', 'Ы': 'Y', 'Ь': '',
            'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
        }
        
        result = []
        for char in text:
            result.append(cyrillic_map.get(char, char))
        
        return ''.join(result)

    def normalize_query(self, query):
        """
        Генерирует варианты поиска, понимая кириллицу и английский.
        """
        variants = []
        
        variants.append(query.strip())
        
        if self.is_cyrillic(query):
            translit = self.smart_transliterate(query)
            if translit != query:
                variants.append(translit)
        
        words = query.split()
        if len(words) > 1:
            variants.append(words[0])
            if len(words) >= 2:
                variants.append(" ".join(words[:2]))
        
        return list(dict.fromkeys(variants))

    def start_search_thread(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        
        self.results_box.delete("0.0", "end")
        self.results_box.insert("0.0", f"🔍 Ищем '{query}'...\n")
        
        threading.Thread(target=self.fetch_search_results, args=(query,), daemon=True).start()

    def fetch_search_results(self, query):
        """
        Поиск в торрент-индексе с поддержкой кириллицы.
        """
        try:
            print(f"🔍 Исходный запрос: '{query}'")
            
            search_variants = self.normalize_query(query)
            print(f"📋 Варианты поиска: {search_variants}")
            
            all_results = []
            
            for variant in search_variants:
                if not variant or len(variant) < 2:
                    continue
                    
                print(f"   Ищем: '{variant}'")
                
                try:
                    encoded_query = urllib.parse.quote(variant)
                    url = f"https://apibay.org/q.php?q={encoded_query}"
                    response = requests.get(url, timeout=10)
                    
                    if response.status_code != 200:
                        print(f"   ⚠️ HTTP {response.status_code}")
                        continue
                    
                    data = response.json()

                    if data and isinstance(data, list) and len(data) > 0 and data[0].get("id") != "0":
                        all_results.extend(data)
                        print(f"   ✅ Найдено {len(data)} результатов")
                    else:
                        print(f"   ❌ Ничего не найдено")
                        
                except requests.exceptions.Timeout:
                    print(f"   ⏱️ Timeout")
                except ValueError as e:
                    print(f"   ⚠️ Ошибка JSON: {e}")
                except Exception as error:
                    print(f"   ⚠️ Ошибка: {error}")
                    continue

            if not all_results:
                self.after(0, lambda: self.results_box.insert(
                    "end", 
                    f"❌ Ничего не найдено по запросу: '{query}'\n\n"
                    f"💡 Попробуйте:\n"
                    f"  • Полное название\n"
                    f"  • На английском\n"
                    f"  • Только ключевые слова\n"
                    f"\n💾 Или загрузите .torrent файл вручную\n"
                ))
                return

            unique_results = {}
            for item in all_results:
                info_hash = item.get("info_hash")
                if info_hash and info_hash not in unique_results:
                    unique_results[info_hash] = item
            
            sorted_results = sorted(
                unique_results.values(),
                key=lambda x: int(x.get("seeders", 0)),
                reverse=True
            )

            self.after(0, lambda: self.results_box.delete("0.0", "end"))
            
            results_header = f"✅ Найдено результатов: {len(sorted_results)}\n\n"
            self.after(0, lambda text=results_header: self.results_box.insert("end", text))
            
            for idx, item in enumerate(sorted_results[:15], 1):
                name = item.get("name", "Неизвестно")
                seeders = int(item.get("seeders", 0))
                leeches = int(item.get("leeches", 0))
                info_hash = item.get("info_hash")
                
                if not info_hash:
                    continue
                
                magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={urllib.parse.quote(name)}"
                
                if seeders > 100:
                    quality_icon = "🟢"
                elif seeders > 10:
                    quality_icon = "🟡"
                else:
                    quality_icon = "🔴"
                
                result_text = (
                    f"{idx}. {quality_icon} {name}\n"
                    f"   👥 Сиды: {seeders} | Пиры: {leeches}\n"
                    f"   🔗 {magnet}\n\n"
                )
                
                self.after(0, lambda text=result_text: self.results_box.insert("end", text))

        except Exception as error:
            error_msg = str(error)
            print(f"Критическая ошибка: {error_msg}")
            self.after(0, lambda msg=error_msg: self.results_box.insert(
                "end", 
                f"❌ Ошибка: {msg}\n"
            ))


    def download_magnet(self):
        uri = self.magnet_entry.get().strip()
        if not uri.startswith("magnet:"):
            messagebox.showwarning("Ошибка", "Это не magnet-ссылка")
            return
        try:
            params = lt.parse_magnet_uri(uri)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось разобрать magnet: {e}")
            return
        self.start_download(params)

    def select_torrent(self):
        path = filedialog.askopenfilename(filetypes=[("Torrent files", "*.torrent")])
        if not path:
            return
        try:
            ti = lt.torrent_info(path)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть торрент: {e}")
            return
        self.file_label.configure(text=f"Выбран: {os.path.basename(path)}", text_color="white")

        params = lt.add_torrent_params()
        params.ti = ti
        self.start_download(params)

    def start_download(self, params):
        if self.is_downloading:
            messagebox.showinfo("Инфо", "Загрузка уже идёт")
            return

        try:
            os.makedirs(self.save_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("Ошибка", f"Не удалось создать папку: {e}")
            return

        params.save_path = self.save_dir
        self.handle = self.ses.add_torrent(params)
        self.is_downloading = True
        self.should_stop = False
        self.is_paused = False
        self.progress = 0.0

        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")

        threading.Thread(target=self.worker, daemon=True).start()


    def worker(self):
        try:
            while not self.should_stop and not self.handle.is_seed():
                if self.should_stop:
                    break

                s = self.handle.status()
                self.progress = s.progress

                if not self.handle.has_metadata():
                    self.status_text = "Получение метаданных (magnet)..."
                else:
                    speed = s.download_rate / 1024 / 1024
                    self.status_text = (
                        f"Прогресс: {s.progress * 100:.1f}% | "
                        f"Скорость: {speed:.2f} МБ/с\n"
                        f"Пиры: {s.num_peers} | Сиды: {s.num_seeds}"
                    )
                time.sleep(1)

            if not self.should_stop:
                self.progress = 1.0
                self.status_text = "✅ Загрузка завершена!"

        except Exception as e:
            if not self.should_stop:
                self.error = str(e)
        finally:
            self.is_downloading = False
            self.pause_btn.configure(state="disabled")
            self.stop_btn.configure(state="disabled")


    def refresh_ui(self):
        self.progress_bar.set(self.progress)
        self.status_label.configure(text=self.status_text)

        if self.error:
            messagebox.showerror("Ошибка", self.error)
            self.error = None

        self.after(300, self.refresh_ui)


    def on_closing(self):
        """Корректное завершение программы"""
        if self.is_downloading:
            response = messagebox.askyesno(
                "Подтверждение",
                "Загрузка в процессе. Вы уверены, что хотите выйти?"
            )
            if not response:
                return

        self.should_stop = True
        if self.handle:
            try:
                self.ses.remove_torrent(self.handle)
            except:
                pass

        print("✅ Программа завершена")
        self.destroy()


if __name__ == "__main__":
    app = TorrentApp()
    app.mainloop()