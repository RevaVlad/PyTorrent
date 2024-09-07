import asyncio
import logging
import tkinter as tk
import tk_async_execute as tae
from pathlib import Path
from tkinter import filedialog, ttk

from main import download_from_torrent_file
from parser import TorrentData
from torrent_statistics import TorrentStatWithVariables


class TorrentInfo(tk.Frame):
    def __init__(self, parent, torrent_data: TorrentData, destination: Path, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)

        self.stat = TorrentStatWithVariables(torrent_data.total_length, torrent_data.total_segments)
        self.torrent_data = torrent_data
        self.destination = destination

        self.name = tk.Label(self, text=f"{torrent_data.torrent_name}")
        self.name.pack(side='left')

        self.bar = ttk.Progressbar(self, maximum=torrent_data.total_length, variable=self.stat.downloadedVar)
        self.bar.pack(side='left')

        self.delete_button = tk.Button(self, text="X", background="red", activebackground="white",
                                       command=self.cancel_download)
        self.delete_button.pack(side='left')

        self.start_download()

    def start_download(self):
        tae.async_execute(download_from_torrent_file(self.torrent_data, self.destination, self.stat), wait=False, visible=False, pop_up=False)

    def cancel_download(self):
        pass


class Torrents(tk.Frame):

    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.torrents = []

    def add_torrent(self, file_location, destination):
        torrent_info = TorrentInfo(self, TorrentData(file_location), Path(destination))
        torrent_info.pack()
        self.torrents.append(torrent_info)


class MainApplication(tk.Frame):

    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

        choose_torrent = tk.Button(self, text="Открыть торрент", command=self.choose_torrent_file)
        choose_torrent.grid(row=0, column=0)

        choose_destination = tk.Button(self, text="Выбрать destination", command=self.choose_destination_folder)
        choose_destination.grid(row=0, column=1)

        self.selected_torrent = tk.StringVar()
        self.selected_torrent.set(r"C:\Users\vladr\PycharmProjects\PyTorrent\torrent_files\test.torrent")
        selected_torrent_label = tk.Label(self, textvariable=self.selected_torrent)
        selected_torrent_label.grid(row=1, column=0)

        self.selected_destination = tk.StringVar()
        self.selected_destination.set(r"C:\Users\vladr\PycharmProjects\PyTorrent\downloaded")
        selected_destination_label = tk.Label(self, textvariable=self.selected_destination)
        selected_destination_label.grid(row=1, column=1)

        start_download = tk.Button(self, text="Начать загрузку", command=self.start_download)
        start_download.grid(row=2, columnspan=2)

        self.torrents = Torrents(self)
        self.torrents.grid(row=3, columnspan=2)

    def choose_torrent_file(self):
        file_path = filedialog.askopenfilename(title="Выберите файл",
                                               filetypes=[("Torrents", "*.torrent"), ("All files", "*.*")])
        if file_path and file_path.endswith(".torrent"):
            self.selected_torrent.set(file_path)

    def choose_destination_folder(self):
        folder = filedialog.askdirectory(title="Выберите destination")
        self.selected_destination.set(folder)

    def start_download(self):
        self.torrents.add_torrent(self.selected_torrent.get(), self.selected_destination.get())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    root = tk.Tk()
    MainApplication(root).pack(side="top", fill="both", expand=True)

    tae.start()
    root.mainloop()
    tae.stop()