import customtkinter as ctk


def walk(widget):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def label_texts(widget):
    return [w.cget("text") for w in walk(widget) if isinstance(w, ctk.CTkLabel)]


def find_buttons(widget, text):
    return [w for w in walk(widget) if isinstance(w, ctk.CTkButton) and w.cget("text") == text]


def button_texts(widget):
    return [w.cget("text") for w in walk(widget) if isinstance(w, ctk.CTkButton)]
