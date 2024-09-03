import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path


class TorrentProgress(tk.Frame):

    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

    def add_torrent(self, file_location, destination):
        pass


class MainApplication(tk.Frame):

    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

        choose_torrent = tk.Button(self, text="Открыть торрент", command=self.choose_torrent_file)
        choose_torrent.grid(row=0, column=0)

        choose_destination = tk.Button(self, text="Выбрать destination", command=self.choose_destination_folder)
        choose_destination.grid(row=0, column=1)

        self.selected_torrent = tk.Label(self, text="")
        self.selected_torrent.grid(row=1, column=0)

        self.selected_destination_label = tk.Label(self, text="")
        self.selected_destination_label.grid(row=1, column=1)

        start_download = tk.Button(self, text="Начать загрузку", command=self.start_download)
        start_download.grid(row=2, columnspan=2)

    def choose_torrent_file(self):
        file_path = filedialog.askopenfilename(title="Выберите файл",
                                               filetypes=[("Torrents", "*.torrent"), ("All files", "*.*")])
        if file_path and file_path.endswith(".torrent"):
            self.selected_torrent.config(text=f"Выбранный файл: {Path(file_path).name}")

    def choose_destination_folder(self):
        folder = filedialog.askdirectory(title="Выберите destination")
        self.selected_destination_label.config(text=f"Выбранная папка: {Path(folder).name}")

    def start_download(self):
        pass


if __name__ == "__main__":
    root = tk.Tk()
    MainApplication(root).pack(side="top", fill="both", expand=True)
    root.mainloop()
