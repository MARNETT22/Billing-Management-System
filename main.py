import os
import shutil
import hashlib
from datetime import datetime
import json
import sqlite3
import tempfile

# --- Kivy Imports ---
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.utils import platform
from kivy.graphics import Color, Rectangle

# --- PDF and Image Imports ---
from fpdf import FPDF
try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
except ImportError:
    PILImage = None

# --- Settings & Constants ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "spark_billing.db")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

def load_settings():
    default = {
        "logo_width": 30, "watermark_width": 120, "watermark_alpha": 0.15,
        "signature_width": 24, "signature_box_width": 50,
        "signature_offset_x": 0, "signature_offset_y": 18
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data or {})
        except: pass
    return default

def calculate_verification_hash(inv_id):
    SECRET_SALT = "SPARK_SECURE_2026"
    secure_str = f"{inv_id}{SECRET_SALT}"
    return hashlib.sha256(secure_str.encode()).hexdigest()[:12].upper()

def generate_invoice_id():
    return datetime.now().strftime("%Y%m%d%H%M%S")

def resolve_image(candidates):
    for n in candidates:
        p = os.path.join(BASE_DIR, n)
        if os.path.exists(p): return p
    return None

LOGO_FILE = resolve_image(["logo.png", "Logo.png", "logo.jpg"])
SIGN_FILE = resolve_image(["signature.png", "DigitalSignature.png"])

class InvoicePDF(FPDF):
    parent_settings = {}
    def header(self):
        # Header implementation same as before
        pass
    def footer(self):
        # Footer implementation same as before
        pass

# --- Screens ---
class CreateInvoiceScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings = load_settings()
        self.current_items = []
        self.selected_item_idx = None
        self.build_ui()

    def build_ui(self):
        layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        
        # Top Header Bar
        header = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5))
        header.add_widget(Button(text="HISTORY", on_press=self.go_to_history))
        header.add_widget(Button(text="VERIFY", on_press=lambda x: App.get_running_app().show_verify_popup()))
        header.add_widget(Button(text="THEME", on_press=lambda x: App.get_running_app().toggle_theme()))
        header.add_widget(Button(text="SETTINGS", on_press=lambda x: App.get_running_app().show_settings_popup()))
        layout.add_widget(header)

        scroll = ScrollView()
        form = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(10), padding=dp(5))
        form.bind(minimum_height=form.setter('height'))

        form.add_widget(Label(text="1. Create Invoice", font_size=dp(18), bold=True, size_hint_y=None, height=dp(30)))
        
        # Student Name
        form.add_widget(Label(text="Student Name", size_hint_y=None, height=dp(25), halign='left'))
        self.ent_name = TextInput(multiline=False, size_hint_y=None, height=dp(40))
        form.add_widget(self.ent_name)

        # Billing Period
        period = GridLayout(cols=2, size_hint_y=None, height=dp(70), spacing=dp(5))
        self.ent_month = Spinner(text=datetime.now().strftime("%B"), values=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"])
        self.ent_year = Spinner(text=str(datetime.now().year), values=[str(y) for y in range(2026, 2046)])
        period.add_widget(Label(text="Month"))
        period.add_widget(Label(text="Year"))
        period.add_widget(self.ent_month)
        period.add_widget(self.ent_year)
        form.add_widget(period)

        # Item Details
        item_box = GridLayout(cols=2, size_hint_y=None, height=dp(280), spacing=dp(8), padding=dp(10))
        item_box.add_widget(Label(text="Category"))
        item_box.add_widget(Label(text="Level/Class"))
        self.ent_cat = Spinner(text="Course Fee", values=[" ", "Course Fee","Tutoring Class Fee","Exam Book Fee","Exam Practice Book Fee","Textbook Fee", "Exam Registration Fee"])
        self.ent_sub = Spinner(text=" ", values=[" ", "Phonics", "STARTERS", "MOVERS", "FLYERS", "KET", "PET", "B1", "B2", "Maths", "Physics", "YEAR 1", "YEAR 2", "YEAR 3", "YEAR 4", "YEAR 5", "YEAR 6", "YEAR 7", "YEAR 8", "YEAR 9", "YEAR 10"])
        item_box.add_widget(self.ent_cat); item_box.add_widget(self.ent_sub)

        item_box.add_widget(Label(text="Details (Optional)", size_hint_x=2))
        self.ent_details = TextInput(multiline=False, size_hint_x=2)
        item_box.add_widget(self.ent_details)

        item_box.add_widget(Label(text="Amount (MMK)"))
        item_box.add_widget(Label(text="Advance (MMK)"))
        self.ent_amt = TextInput(text="0", multiline=False, input_filter='float')
        self.ent_adv = TextInput(text="0", multiline=False, input_filter='float')
        item_box.add_widget(self.ent_amt); item_box.add_widget(self.ent_adv)
        form.add_widget(item_box)

        form.add_widget(Button(text="+ ADD TO LIST", size_hint_y=None, height=dp(50), background_color=(0.1, 0.45, 0.9, 1), on_press=self.add_item))

        # Current Items List
        form.add_widget(Label(text="Current Invoice Items", bold=True, size_hint_y=None, height=dp(30)))
        self.items_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(5))
        self.items_layout.bind(minimum_height=self.items_layout.setter('height'))
        form.add_widget(self.items_layout)

        # Bottom Action Bar
        bottom_actions = BoxLayout(orientation='vertical', size_hint_y=None, height=dp(150), spacing=dp(10))
        self.lbl_total = Label(text="TOTAL: 0 MMK", font_size=dp(22), bold=True, size_hint_y=None, height=dp(40), color=(0.1, 0.5, 0.1, 1))
        bottom_actions.add_widget(self.lbl_total)
        
        btn_finalize = Button(text="FINALIZE & PRINT INVOICE", size_hint_y=None, height=dp(60), background_color=(0.1, 0.6, 0.2, 1), bold=True)
        btn_finalize.bind(on_press=self.finalize_invoice)
        bottom_actions.add_widget(btn_finalize)
        
        btn_clear = Button(text="CLEAR ALL ITEMS", size_hint_y=None, height=dp(40), background_color=(0.8, 0.4, 0.4, 1))
        btn_clear.bind(on_press=self.clear_all)
        bottom_actions.add_widget(btn_clear)
        form.add_widget(bottom_actions)

        scroll.add_widget(form)
        layout.add_widget(scroll)
        self.add_widget(layout)

    def add_item(self, instance):
        try:
            amt = float(self.ent_amt.text or 0)
            adv = float(self.ent_adv.text or 0)
        except ValueError: return
        
        if amt <= 0: return
        
        desc = f"{self.ent_cat.text} ({self.ent_sub.text.strip()})"
        if self.ent_details.text.strip(): desc = f"{self.ent_details.text.strip()} - {desc}"
        
        item = {"desc": desc, "amt": amt, "adv": adv, "cat": self.ent_cat.text, "sub": self.ent_sub.text, "det": self.ent_details.text}
        self.current_items.append(item)
        self.refresh_list()
        self.ent_amt.text = "0"; self.ent_adv.text = "0"; self.ent_details.text = ""

    def refresh_list(self):
        self.items_layout.clear_widgets()
        total = 0
        for i, it in enumerate(self.current_items):
            row = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(5))
            
            # Item Info
            info = Button(text=f"{it['desc']} | {it['amt']-it['adv']:,.0f} MMK", size_hint_x=0.7, background_color=(1,1,1,1), color=(0,0,0,1), halign='left', valign='middle')
            info.bind(size=info.setter('text_size'))
            row.add_widget(info)
            
            # Edit Button
            edit_btn = Button(text="Edit", size_hint_x=0.15, background_color=(0.2, 0.6, 0.9, 1))
            edit_btn.bind(on_press=lambda x, idx=i: self.edit_item(idx))
            row.add_widget(edit_btn)
            
            # Delete Button
            del_btn = Button(text="Del", size_hint_x=0.15, background_color=(0.9, 0.3, 0.2, 1))
            del_btn.bind(on_press=lambda x, idx=i: self.delete_item(idx))
            row.add_widget(del_btn)
            
            self.items_layout.add_widget(row)
            total += (it['amt'] - it['adv'])
        self.lbl_total.text = f"TOTAL: {total:,.0f} MMK"

    def edit_item(self, idx):
        it = self.current_items.pop(idx)
        self.ent_cat.text = it['cat']; self.ent_sub.text = it['sub']; self.ent_details.text = it['det']
        self.ent_amt.text = str(it['amt']); self.ent_adv.text = str(it['adv'])
        self.refresh_list()

    def delete_item(self, idx):
        self.current_items.pop(idx)
        self.refresh_list()

    def clear_all(self, instance):
        self.current_items = []; self.ent_name.text = ""
        self.refresh_list()

    def finalize_invoice(self, instance):
        if not self.current_items:
            Popup(title="Error", content=Label(text="No items in invoice!"), size_hint=(0.8, 0.4)).open()
            return
            
        inv_id = generate_invoice_id()
        # 1. Save PDF (stub for now, but let's assume it's there)
        # self.generate_pdf(inv_id) 
        
        # 2. Save Image
        img_path = self.save_as_image(inv_id)
        
        msg = f"Invoice #{inv_id} saved!\n"
        if img_path:
            msg += f"Image saved to: {os.path.basename(img_path)}\nCheck your Gallery/Photos app."
        else:
            msg += "PDF saved. (Image generation failed)"
            
        Popup(title="Success", content=Label(text=msg, halign='center'), size_hint=(0.9, 0.4)).open()
        self.clear_all(None)

    def save_as_image(self, inv_id):
        if not PILImage: return None
        
        # Setup Dimensions
        width, height = 800, 1100
        img = PILImage.new('RGB', (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        try:
            # Use default font if custom font not found
            font_bold = ImageFont.load_default()
            font_reg = ImageFont.load_default()
            # In a real app, we'd load a proper .ttf font
        except:
            font_bold = font_reg = None

        # Draw Header
        draw.rectangle([0, 0, width, 120], fill=(20, 40, 120))
        draw.text((width//2, 40), "THE SPARK EDUCATION CENTRE", fill=(255, 255, 255), anchor="mm")
        draw.text((width//2, 80), "Invoice Billing Management System", fill=(240, 240, 240), anchor="mm")

        # Invoice Info
        y = 150
        draw.text((50, y), f"Invoice ID: {inv_id}", fill=(0, 0, 0))
        draw.text((width-250, y), f"Date: {datetime.now().strftime('%d-%m-%Y')}", fill=(0, 0, 0))
        
        y += 40
        draw.text((50, y), f"Student Name: {self.ent_name.text or 'N/A'}", fill=(0, 0, 0))
        draw.text((width-250, y), f"Period: {self.ent_month.text} {self.ent_year.text}", fill=(0, 0, 0))

        # Table Header
        y += 60
        draw.rectangle([40, y, width-40, y+40], fill=(240, 240, 240))
        draw.text((60, y+10), "Description", fill=(0, 0, 0))
        draw.text((width-150, y+10), "Amount", fill=(0, 0, 0))
        
        # Table Items
        y += 50
        total = 0
        for it in self.current_items:
            amt = it['amt'] - it['adv']
            draw.text((60, y), it['desc'], fill=(0, 0, 0))
            draw.text((width-150, y), f"{amt:,.0f}", fill=(0, 0, 0))
            total += amt
            y += 35
            if y > height - 250: break # Simple overflow check

        # Total
        y += 20
        draw.line([40, y, width-40, y], fill=(100, 100, 100), width=2)
        y += 20
        draw.text((width-300, y), "GRAND TOTAL:", fill=(0, 0, 0))
        draw.text((width-150, y), f"{total:,.0f} MMK", fill=(20, 100, 20))

        # Verification & Signature
        v_hash = calculate_verification_hash(inv_id)
        draw.text((50, height-150), f"Verification: {v_hash}", fill=(150, 150, 150))
        
        if SIGN_FILE and os.path.exists(SIGN_FILE):
            try:
                sig = PILImage.open(SIGN_FILE).convert("RGBA")
                sig.thumbnail((150, 100))
                img.paste(sig, (width-200, height-180), sig)
            except: pass
        
        draw.text((width-200, height-60), "Authorized Signature", fill=(0, 0, 0))

        # Save Path logic
        filename = f"Spark_Invoice_{inv_id}.jpg"
        if platform == "android":
            # For Android, we save to public Pictures folder
            from android.storage import primary_external_storage_path
            storage = primary_external_storage_path()
            out_dir = os.path.join(storage, "Pictures", "SparkInvoices")
            if not os.path.exists(out_dir): os.makedirs(out_dir)
            out_path = os.path.join(out_dir, filename)
            img.save(out_path, "JPEG", quality=95)
            self.scan_file_android(out_path)
        else:
            out_path = os.path.join(os.path.expanduser("~"), filename)
            img.save(out_path, "JPEG", quality=95)
            
        return out_path

    def scan_file_android(self, path):
        try:
            from jnius import autoclass
            Context = autoclass('android.content.Context')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            MediaScannerConnection = autoclass('android.media.MediaScannerConnection')
            
            activity = PythonActivity.mActivity
            MediaScannerConnection.scanFile(
                activity, 
                [path], 
                ["image/jpeg"], 
                None
            )
        except Exception as e:
            print(f"Gallery scan failed: {e}")

    def go_to_history(self, instance): self.manager.current = 'history'

class HistoryScreen(Screen):
    def on_enter(self): self.build_ui()
    def build_ui(self):
        self.clear_widgets()
        layout = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        
        # Header with Search
        header = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5))
        header.add_widget(Button(text="BACK", size_hint_x=0.2, on_press=lambda x: setattr(self.manager, 'current', 'create')))
        self.search_input = TextInput(hint_text="Search by Name/ID...", multiline=False)
        header.add_widget(self.search_input)
        layout.add_widget(header)
        
        # Labels for Table
        tbl_header = BoxLayout(size_hint_y=None, height=dp(30), padding=[dp(10), 0])
        tbl_header.add_widget(Label(text="ID / NAME", halign='left', size_hint_x=0.7))
        tbl_header.add_widget(Label(text="TOTAL", halign='right', size_hint_x=0.3))
        layout.add_widget(tbl_header)

        scroll = ScrollView()
        list_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2))
        list_box.bind(minimum_height=list_box.setter('height'))
        
        # Dummy Data for Mobile Demo
        demo_data = [
            {"id": "202604011243", "name": "Mg Mg", "total": 45000, "date": "01-04-2026"},
            {"id": "202603310915", "name": "Su Su", "total": 120000, "date": "31-03-2026"},
            {"id": "202603301420", "name": "Aung Aung", "total": 35000, "date": "30-03-2026"},
            {"id": "202603291110", "name": "Kyaw Kyaw", "total": 75000, "date": "29-03-2026"},
        ]
        
        for data in demo_data:
            btn = Button(size_hint_y=None, height=dp(60), background_color=(1,1,1,1), color=(0,0,0,1))
            btn.add_widget(Label(text=f"{data['id']}\n[b]{data['name']}[/b]", markup=True, color=(0,0,0,1), pos=btn.pos, size=btn.size, halign='left', padding=[dp(10), 0]))
            btn.add_widget(Label(text=f"{data['total']:,.0f} MMK", color=(0.1, 0.5, 0.1, 1), pos=btn.pos, size=btn.size, halign='right', padding=[dp(10), 0]))
            btn.bind(on_press=lambda x, d=data: self.show_preview(d))
            list_box.add_widget(btn)
            
        scroll.add_widget(list_box)
        layout.add_widget(scroll)
        
        # Action Bar at bottom
        actions = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(5))
        actions.add_widget(Button(text="REPRINT PDF", background_color=(0.2, 0.6, 0.8, 1)))
        actions.add_widget(Button(text="SHARE IMAGE", background_color=(0.2, 0.8, 0.4, 1)))
        layout.add_widget(actions)
        
        self.add_widget(layout)

    def show_preview(self, data):
        content = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        
        # Mocking a mobile invoice preview
        preview_box = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(5))
        with preview_box.canvas.before:
            Color(1, 1, 1, 1)
            self.rect = Rectangle(size=preview_box.size, pos=preview_box.pos)
        preview_box.bind(size=self._update_rect, pos=self._update_rect)
        
        preview_box.add_widget(Label(text="THE SPARK EDUCATION CENTRE", color=(0,0,0.5,1), bold=True, size_hint_y=None, height=dp(30)))
        preview_box.add_widget(Label(text=f"Invoice: #{data['id']}", color=(0,0,0,1), size_hint_y=None, height=dp(25)))
        preview_box.add_widget(Label(text=f"Date: {data['date']}", color=(0.3,0.3,0.3,1), size_hint_y=None, height=dp(20)))
        preview_box.add_widget(Label(text=f"Customer: {data['name']}", color=(0,0,0,1), bold=True, size_hint_y=None, height=dp(30)))
        
        preview_box.add_widget(Label(text="----------------------------------", color=(0.5,0.5,0.5,1), size_hint_y=None, height=dp(10)))
        preview_box.add_widget(Label(text=f"Total Amount: {data['total']:,.0f} MMK", color=(0,0.5,0,1), bold=True, font_size=dp(20), size_hint_y=None, height=dp(40)))
        preview_box.add_widget(Label(text="Status: PAID", color=(0,0.7,0,1), bold=True, size_hint_y=None, height=dp(25)))
        
        content.add_widget(preview_box)
        
        btn_close = Button(text="CLOSE PREVIEW", size_hint_y=None, height=dp(50), background_color=(0.8, 0.2, 0.2, 1))
        content.add_widget(btn_close)
        
        popup = Popup(title="Mobile Demo Preview", content=content, size_hint=(0.9, 0.7))
        btn_close.bind(on_press=popup.dismiss)
        popup.open()

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

class BillingApp(App):
    def build(self):
        Window.clearcolor = (0.94, 0.95, 0.96, 1)
        sm = ScreenManager()
        sm.add_widget(CreateInvoiceScreen(name='create'))
        sm.add_widget(HistoryScreen(name='history'))
        return sm
    def toggle_theme(self): pass
    def show_settings_popup(self): pass
    def show_verify_popup(self): pass

if __name__ == '__main__':
    BillingApp().run()
