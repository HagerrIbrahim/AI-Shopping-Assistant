
import json
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from PIL import Image, ImageTk
from io import BytesIO


# Path of the new dataset
DATASET_PATH = r"C:\Users\DELL\Downloads\meta_Amazon_Fashion.jsonl\meta_Amazon_Fashion.jsonl"


def load_first_products(file_path, count=5):
    products = []

    # Read only the first 5 products
    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                products.append(json.loads(line))

                if len(products) == count:
                    break

    return products


def display_value(value):
    if value is None:
        return ""
    return str(value)


def show_product_details(event=None):
    global current_images, current_image_index

    selected = tree.selection()

    if not selected:
        return

    index = int(selected[0])
    product = products[index]

    # Display all product details
    details_text.delete("1.0", tk.END)
    details_text.insert(
        tk.END,
        json.dumps(product, ensure_ascii=False, indent=2)
    )

    # Get product images
    current_images = product.get("images") or []
    current_image_index = 0

    display_image()


def display_image():
    global photo_reference

    if not current_images:
        image_label.configure(
            image="",
            text="No images available"
        )
        image_counter.configure(text="0 / 0")
        previous_button.configure(state="disabled")
        next_button.configure(state="disabled")
        return

    image_data = current_images[current_image_index]

    # Prefer high-resolution image
    image_url = (
        image_data.get("hi_res")
        or image_data.get("large")
        or image_data.get("thumb")
    )

    if not image_url:
        image_label.configure(
            image="",
            text="Image URL unavailable"
        )
        image_counter.configure(
            text=f"{current_image_index + 1} / {len(current_images)}"
        )
        return

    try:
        response = requests.get(image_url, timeout=15)
        response.raise_for_status()

        image = Image.open(BytesIO(response.content))
        image.thumbnail((300, 250))

        photo_reference = ImageTk.PhotoImage(image)

        image_label.configure(
            image=photo_reference,
            text=""
        )

        image_counter.configure(
            text=f"{current_image_index + 1} / {len(current_images)}"
        )

        previous_button.configure(
            state="normal" if current_image_index > 0 else "disabled"
        )

        next_button.configure(
            state=(
                "normal"
                if current_image_index < len(current_images) - 1
                else "disabled"
            )
        )

    except Exception as error:
        image_label.configure(
            image="",
            text=f"Could not load image:\n{error}"
        )

        image_counter.configure(
            text=f"{current_image_index + 1} / {len(current_images)}"
        )


def change_image(step):
    global current_image_index

    new_index = current_image_index + step

    if 0 <= new_index < len(current_images):
        current_image_index = new_index
        display_image()


# Load products
try:
    products = load_first_products(DATASET_PATH)

    if not products:
        raise ValueError("No products were found in the file.")

except Exception as error:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Dataset Error", str(error))
    root.destroy()
    raise SystemExit


# Current image variables
current_images = []
current_image_index = 0
photo_reference = None


# Create the GUI
root = tk.Tk()
root.title("Amazon Fashion Dataset Preview")
root.geometry("1200x850")


title_label = ttk.Label(
    root,
    text="Amazon Fashion - First 5 Products",
    font=("Arial", 16, "bold")
)
title_label.pack(pady=10)


# Products table
table_frame = ttk.Frame(root)
table_frame.pack(fill="x", padx=10, pady=5)

columns = (
    "parent_asin",
    "title",
    "main_category",
    "price",
    "average_rating"
)

tree = ttk.Treeview(
    table_frame,
    columns=columns,
    show="headings",
    height=5
)

tree.heading("parent_asin", text="Parent ASIN")
tree.heading("title", text="Title")
tree.heading("main_category", text="Main Category")
tree.heading("price", text="Price")
tree.heading("average_rating", text="Rating")

tree.column("parent_asin", width=130)
tree.column("title", width=420)
tree.column("main_category", width=180)
tree.column("price", width=100)
tree.column("average_rating", width=100)

scrollbar = ttk.Scrollbar(
    table_frame,
    orient="vertical",
    command=tree.yview
)

tree.configure(yscrollcommand=scrollbar.set)

tree.pack(side="left", fill="x", expand=True)
scrollbar.pack(side="right", fill="y")


# Add products to the table
for index, product in enumerate(products):
    tree.insert(
        "",
        "end",
        iid=str(index),
        values=(
            display_value(product.get("parent_asin")),
            display_value(product.get("title")),
            display_value(product.get("main_category")),
            display_value(product.get("price")),
            display_value(product.get("average_rating"))
        )
    )


# Product images section
image_frame = ttk.LabelFrame(root, text="Product Images")
image_frame.pack(fill="x", padx=10, pady=5)

image_label = ttk.Label(
    image_frame,
    text="Select a product"
)
image_label.pack(pady=5)

image_buttons = ttk.Frame(image_frame)
image_buttons.pack(pady=5)

previous_button = ttk.Button(
    image_buttons,
    text="Previous",
    command=lambda: change_image(-1),
    state="disabled"
)
previous_button.pack(side="left", padx=5)

image_counter = ttk.Label(
    image_buttons,
    text="0 / 0"
)
image_counter.pack(side="left", padx=10)

next_button = ttk.Button(
    image_buttons,
    text="Next",
    command=lambda: change_image(1),
    state="disabled"
)
next_button.pack(side="left", padx=5)


# Product details section
details_label = ttk.Label(
    root,
    text="Full Product Details",
    font=("Arial", 12, "bold")
)
details_label.pack(pady=(10, 5))

details_frame = ttk.Frame(root)
details_frame.pack(fill="both", expand=True, padx=10, pady=5)

details_text = tk.Text(
    details_frame,
    wrap="word",
    font=("Consolas", 10)
)

details_scrollbar = ttk.Scrollbar(
    details_frame,
    orient="vertical",
    command=details_text.yview
)

details_text.configure(
    yscrollcommand=details_scrollbar.set
)

details_text.pack(side="left", fill="both", expand=True)
details_scrollbar.pack(side="right", fill="y")


# When selecting a product, display its details and images
tree.bind("<<TreeviewSelect>>", show_product_details)


# Select the first product automatically
if products:
    tree.selection_set("0")
    show_product_details()


root.mainloop()
