import logging
import sys

import configuration
import tkinter as tk
import tk_async_execute as tae

from pathlib import Path
from tkinter import filedialog, ttk

from main import TorrentApplication
from parser import TorrentData
from torrent_statistics import TorrentStatWithVariables


class TorrentInfo(tk.Frame):
    def __init__(self, parent, download_window, data, stat, total_length, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)

        self.stat = stat
        self.download_window = download_window

        self.name = tk.Label(self, text=f"{data.torrent_name}")
        self.name.pack(side='left')

        self.bar = ttk.Progressbar(self, maximum=total_length, variable=self.stat.downloadedVar)
        self.bar.pack(side='left')

        self.delete_button = tk.Button(self, text="X", background="red", activebackground="white",
                                       command=self.destroy)
        self.delete_button.pack(side='left')

    def cancel_download(self):
        self.download_window.future.cancel()
        self.download_window.destroy()

    def destroy(self):
        self.cancel_download()
        tk.Frame.destroy(self)


class Torrents(tk.Frame):

    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        self.client = TorrentApplication()
        self.torrents_frames = []

    def add_torrent(self, file_location, destination):
        torrent_data = TorrentData(file_location)
        self._choose_files(torrent_data, destination)

    def _choose_files(self, torrent_data, destination):
        popup = tk.Toplevel()

        total_length = 0
        variables = [tk.BooleanVar(popup, True) for _ in range(len(torrent_data.files))]
        for index, file in enumerate(torrent_data.files):
            filepath = file['path']
            tk.Checkbutton(popup, variable=variables[index], text=filepath).grid()

        btn = tk.Button(popup, text="Start", command=lambda: self._start_download(torrent_data, destination, variables)
                                                             or popup.destroy())
        btn.grid()

    def _start_download(self, torrent_data, destination, variables):
        selected_files = [file['path'][-1] for index, file in enumerate(torrent_data.files) if variables[index].get()]
        total_length = sum(file['length'] for index, file in enumerate(selected_files) if variables[index].get())
        if len(selected_files) == 0:
            return

        torrent_stat = TorrentStatWithVariables(torrent_data.total_length, torrent_data.total_segments)
        download_window = tae.async_execute(self.client.download(torrent_data,
                                                                 Path(destination),
                                                                 torrent_stat,
                                                                 selected_files=selected_files),
                                            pop_up=False, wait=False, visible=False,
                                            master=self)
        torrent_info = TorrentInfo(self, download_window, torrent_data, torrent_stat, total_length)
        torrent_info.pack()

        self.torrents_frames.append(torrent_info)

    def destroy(self):
        self.client.close()
        tk.Frame.destroy(self)


class MainApplication(tk.Frame):

    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent

        choose_torrent = tk.Button(self, text="Открыть торрент", command=self.choose_torrent_file)
        choose_torrent.grid(row=0, column=0)

        choose_destination = tk.Button(self, text="Выбрать destination", command=self.choose_destination_folder)
        choose_destination.grid(row=0, column=1)

        project_directory = Path(sys.path[0])

        self.selected_torrent = tk.StringVar()
        self.selected_torrent.set(str(project_directory / "torrent_files" / "test.torrent"))
        selected_torrent_label = tk.Label(self, textvariable=self.selected_torrent)
        selected_torrent_label.grid(row=1, column=0)

        self.selected_destination = tk.StringVar()
        self.selected_destination.set(str(project_directory / "downloaded"))
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
    logging.basicConfig(level=configuration.LOGGING_LEVEL)

    root = tk.Tk()
    MainApplication(root).pack(side="top", fill="both", expand=True)

    tae.start()
    root.mainloop()
    tae.stop()
