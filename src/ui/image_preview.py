import tkinter as tk

import customtkinter as ctk

from src.ui import theme


class ImagePreview(ctk.CTkToplevel):
    def __init__(self, master, image, title: str):
        super().__init__(master)
        self.title(title)
        self.configure(fg_color=theme.BACKGROUND)
        self.transient(master)
        label = ctk.CTkLabel(self, text="", image=image, cursor="hand2")
        label.pack(padx=14, pady=14)
        for widget in (self, label):
            widget.bind("<Button-1>", lambda _event: self.destroy())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.after(150, self._finish_setup)

    def _finish_setup(self):
        try:
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass
