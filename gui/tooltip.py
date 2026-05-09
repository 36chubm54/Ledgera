import tkinter as tk


def _calculate_tooltip_position(
    *,
    preferred_x: int,
    preferred_y_bottom: int,
    widget_top_y: int,
    tooltip_width: int,
    tooltip_height: int,
    boundary_left: int,
    boundary_right: int,
    boundary_top: int,
    boundary_bottom: int,
) -> tuple[int, int]:
    x = preferred_x
    if x + tooltip_width > boundary_right:
        x = boundary_right - tooltip_width
    if x < boundary_left:
        x = boundary_left

    y_top = widget_top_y - tooltip_height - 5
    y_bottom_fits = (
        preferred_y_bottom + tooltip_height <= boundary_bottom
        and preferred_y_bottom >= boundary_top
    )
    y_top_fits = y_top + tooltip_height <= boundary_bottom and y_top >= boundary_top

    if y_bottom_fits:
        y = preferred_y_bottom
    elif y_top_fits:
        y = y_top
    else:
        y = max(boundary_top, min(preferred_y_bottom, boundary_bottom - tooltip_height))

    if y + tooltip_height > boundary_bottom:
        y = boundary_bottom - tooltip_height
    if y < boundary_top:
        y = boundary_top
    return x, y


def show_popup_tooltip(
    *,
    owner: tk.Widget,
    text: str,
    preferred_x: int,
    preferred_y_bottom: int,
    widget_top_y: int,
    wraplength: int = 320,
    background: str = "#ffffe1",
    borderwidth: int = 1,
    padx: int = 2,
    pady: int = 1,
) -> tk.Toplevel:
    tooltip = tk.Toplevel(owner)
    tooltip.withdraw()
    tooltip.wm_overrideredirect(True)
    label = tk.Label(
        tooltip,
        text=text,
        justify=tk.LEFT,
        background=background,
        relief=tk.SOLID,
        borderwidth=borderwidth,
        font=("Segoe UI", 9),
        wraplength=wraplength,
    )
    label.pack(ipadx=padx, ipady=pady)
    tooltip.update_idletasks()

    root = owner.winfo_toplevel()
    x, y = _calculate_tooltip_position(
        preferred_x=preferred_x,
        preferred_y_bottom=preferred_y_bottom,
        widget_top_y=widget_top_y,
        tooltip_width=tooltip.winfo_width(),
        tooltip_height=tooltip.winfo_height(),
        boundary_left=root.winfo_rootx(),
        boundary_right=min(root.winfo_rootx() + root.winfo_width(), owner.winfo_screenwidth()),
        boundary_top=root.winfo_rooty(),
        boundary_bottom=min(
            root.winfo_rooty() + root.winfo_height(),
            owner.winfo_screenheight(),
        ),
    )
    tooltip.wm_geometry(f"+{x}+{y}")
    tooltip.deiconify()
    return tooltip


class Tooltip:
    """Простой Tooltip для tkinter/ttk виджетов."""

    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def showtip(self):
        if self.tipwindow:
            return
        # Исходная позиция подсказки (ниже и справа от виджета)
        x = self.widget.winfo_rootx() + 20
        y_bottom = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.withdraw()  # Скрыть окно до установки позиции
        tw.wm_overrideredirect(True)
        # Создаём label, чтобы вычислить размеры подсказки
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe1",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        label.pack(ipadx=1)
        tw.update_idletasks()  # Обновляем геометрию для получения размеров
        tw_width = tw.winfo_width()
        tw_height = tw.winfo_height()

        # Получаем границы корневого окна
        root = self.widget.winfo_toplevel()
        root_x = root.winfo_rootx()
        root_y = root.winfo_rooty()
        root_width = root.winfo_width()
        root_height = root.winfo_height()

        # Границы экрана
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()

        # Вычисляем допустимые границы (окно приложения, без жёсткого clamp к primary screen)
        left_boundary = root_x
        right_boundary = min(root_x + root_width, screen_width)
        top_boundary = root_y
        bottom_boundary = min(root_y + root_height, screen_height)

        x, y = _calculate_tooltip_position(
            preferred_x=x,
            preferred_y_bottom=y_bottom,
            widget_top_y=self.widget.winfo_rooty(),
            tooltip_width=tw_width,
            tooltip_height=tw_height,
            boundary_left=left_boundary,
            boundary_right=right_boundary,
            boundary_top=top_boundary,
            boundary_bottom=bottom_boundary,
        )

        tw.wm_geometry(f"+{x}+{y}")
        tw.deiconify()  # Показать окно после установки позиции

    def hidetip(self):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None
