import kivy
from kivy.config import Config
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '480')
Config.set('graphics', 'resizable', '0')

from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.slider import Slider
from kivy.clock import Clock
import requests
import threading  # <-- Solución definitiva para el lag en los sliders

try:
    from plyer import accelerometer
    ACCEL_DISPONIBLE = True
except Exception:
    ACCEL_DISPONIBLE = False

class FrenoSlider(Slider):
    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) or touch.ud.get('freno_active', False):
            touch.ud['freno_active'] = False
            Clock.schedule_once(lambda dt: setattr(self, 'value', 0.0), 0)
            return True
        return super(FrenoSlider, self).on_touch_up(touch)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.ud['freno_active'] = True
        return super(FrenoSlider, self).on_touch_down(touch)

class AcelSlider(Slider):
    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos) or touch.ud.get('acel_active', False):
            touch.ud['acel_active'] = False
            Clock.schedule_once(lambda dt: setattr(self, 'value', 0.0), 0)
            return True
        return super(AcelSlider, self).on_touch_up(touch)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.ud['acel_active'] = True
        return super(AcelSlider, self).on_touch_down(touch)

class VolanteAppUI(FloatLayout):
    def __init__(self, **kwargs):
        super(VolanteAppUI, self).__init__(**kwargs)
        
        self.offset_centro = 0.0
        self.giro_suavizado = 0.0
        self.sensor_activo = False
        
        self.marcha_actual = 1
        self.sistema_marchas_activo = True
        self.embrague_presionado = 0.0  # Estado del embrague
        
        self.PC_IP = "192.168.1.50" 
        self.PC_PORT = 5000

        # ==================== 1. CABECERA SUPERIOR PROFESIONAL ====================
        self.barra_giro = Slider(
            min=-5.0, max=5.0, value=0.0, disabled=True, 
            size_hint=(1, 0.12), pos_hint={'top': 1.0, 'center_x': 0.5}
        )
        self.add_widget(self.barra_giro)

        self.label_estado = Label(
            text="Estado: Buscando servidor en PC...", 
            font_size=12, color=(1, 0.5, 0, 1), size_hint=(0.5, 0.08),
            pos_hint={'top': 0.88, 'center_x': 0.5}
        )
        self.add_widget(self.label_estado)

        self.btn_sensor = Button(
            text="CALIBRAR", font_size=12, size_hint=(None, None), size=(95, 40),
            pos_hint={'top': 0.98, 'left': 0.02}
        )
        self.btn_sensor.bind(on_press=self.calibrar_y_activar)
        self.add_widget(self.btn_sensor)

        self.btn_toggle_marchas = Button(
            text="MARCHAS [ON]", font_size=10, size_hint=(None, None), size=(110, 40),
            pos_hint={'top': 0.98, 'right': 0.98}
        )
        self.btn_toggle_marchas.bind(on_press=self.toggle_sistema_marchas)
        self.add_widget(self.btn_toggle_marchas)

        # ==================== 2. ZONA INFERIOR: MATRIZ SIMÉTRICA ====================
        inferior_layout = GridLayout(
            cols=3, 
            spacing=40, 
            padding=[30, 10, 30, 10], 
            size_hint=(0.9, 0.68), 
            pos_hint={'center_x': 0.5, 'y': 0.05}
        )

        # --- COLUMNA 1: EMBRAGUE + BOTÓN '-' (Arriba) Y FRENO ---
        freno_grupo = BoxLayout(orientation='horizontal', spacing=10, size_hint=(1, 1))
        
        # Columna vertical para los botones de la izquierda (Embrague arriba, '-' abajo)
        botones_izq_box = BoxLayout(orientation='vertical', spacing=10, size_hint=(None, None), size=(50, 110), pos_hint={'center_y': 0.5})
        
        self.btn_embrague = Button(text="EMB", font_size=12, bold=True, size_hint=(None, None), size=(50, 50))
        self.btn_embrague.bind(on_press=self.presionar_embrague, on_release=self.soltar_embrague)
        botones_izq_box.add_widget(self.btn_embrague)

        self.btn_bajar_marcha = Button(text="-", font_size=26, bold=True, size_hint=(None, None), size=(50, 50))
        self.btn_bajar_marcha.bind(on_press=self.bajar_marcha)
        botones_izq_box.add_widget(self.btn_bajar_marcha)

        freno_grupo.add_widget(botones_izq_box)

        freno_box = BoxLayout(orientation='vertical', size_hint=(1, 1))
        freno_box.add_widget(Label(text="FRENO", font_size=13, size_hint=(1, 0.2)))
        self.slider_freno = FrenoSlider(min=0.0, max=100.0, value=0.0, orientation='vertical', size_hint=(1, 0.8))
        freno_box.add_widget(self.slider_freno)
        freno_grupo.add_widget(freno_box)
        
        inferior_layout.add_widget(freno_grupo)

        # --- COLUMNA 2: TABLERO DIGITAL CENTRAL + SHIFT LIGHTS ---
        dash_box = BoxLayout(orientation='vertical', spacing=4, size_hint=(1, 1), padding=(0, 5, 0, 5))
        
        self.lbl_velocidad = Label(text="0", font_size=34, bold=True, color=(0, 1, 1, 1), size_hint=(1, 0.35))
        dash_box.add_widget(self.lbl_velocidad)
        
        self.lbl_marcha_dash = Label(text="1", font_size=32, bold=True, color=(1, 1, 0, 1), size_hint=(1, 0.35))
        dash_box.add_widget(self.lbl_marcha_dash)

        self.slider_rpm = Slider(min=0, max=8000, value=0, disabled=True, size_hint=(1, 0.3))
        dash_box.add_widget(self.slider_rpm)
        
        inferior_layout.add_widget(dash_box)

        # --- COLUMNA 3: ACELERADOR Y BOTÓN '+' ---
        acel_grupo = BoxLayout(orientation='horizontal', spacing=10, size_hint=(1, 1))

        acel_box = BoxLayout(orientation='vertical', size_hint=(1, 1))
        acel_box.add_widget(Label(text="ACELERADOR", font_size=13, size_hint=(1, 0.2)))
        self.slider_acel = AcelSlider(min=0.0, max=100.0, value=0.0, orientation='vertical', size_hint=(1, 0.8))
        acel_box.add_widget(self.slider_acel)
        acel_grupo.add_widget(acel_box)

        self.btn_subir_marcha = Button(text="+", font_size=26, bold=True, size_hint=(None, None), size=(50, 50), pos_hint={'center_y': 0.5})
        self.btn_subir_marcha.bind(on_press=self.subir_marcha)
        acel_grupo.add_widget(self.btn_subir_marcha)

        inferior_layout.add_widget(acel_grupo)

        self.add_widget(inferior_layout)

    def toggle_sistema_marchas(self, instance):
        self.sistema_marchas_activo = not self.sistema_marchas_activo
        if self.sistema_marchas_activo:
            self.btn_toggle_marchas.text = "MARCHAS [ON]"
            self.btn_subir_marcha.disabled = False
            self.btn_bajar_marcha.disabled = False
            self.btn_embrague.disabled = False
        else:
            self.btn_toggle_marchas.text = "MARCHAS [OFF]"
            self.btn_subir_marcha.disabled = True
            self.btn_bajar_marcha.disabled = True
            self.btn_embrague.disabled = True

    def presionar_embrague(self, instance):
        self.embrague_presionado = 100.0
        self.btn_embrague.background_color = (0.2, 0.8, 0.2, 1)

    def soltar_embrague(self, instance):
        self.embrague_presionado = 0.0
        self.btn_embrague.background_color = (1, 1, 1, 1)

    def subir_marcha(self, instance):
        if self.sistema_marchas_activo and self.marcha_actual < 6:
            self.marcha_actual += 1
            self.actualizar_texto_marcha()

    def bajar_marcha(self, instance):
        if self.sistema_marchas_activo and self.marcha_actual > -1:
            self.marcha_actual -= 1
            self.actualizar_texto_marcha()

    def actualizar_texto_marcha(self):
        if self.marcha_actual == 0:
            txt = "N"
        elif self.marcha_actual == -1:
            txt = "R"
        else:
            txt = str(self.marcha_actual)
        self.lbl_marcha_dash.text = txt

    def calibrar_y_activar(self, instance):
        if ACCEL_DISPONIBLE:
            try:
                accelerometer.enable()
                val = accelerometer.acceleration
                if val and len(val) > 1 and val[1] is not None:
                    self.offset_centro = val[1]
                elif val and len(val) > 0 and val[0] is not None:
                    self.offset_centro = val[0]
                
                self.sensor_activo = True
                self.btn_sensor.text = "ACTIVO"
                Clock.schedule_interval(self.enviar_datos_pc, 0.05)
            except Exception:
                self.label_estado.text = "Error al calibrar sensor"
        else:
            self.label_estado.text = "Plyer no disponible"

    def enviar_datos_pc(self, dt):
        giro_bruto = 0.0
        if self.sensor_activo:
            try:
                val = accelerometer.acceleration
                if val and len(val) > 1 and val[1] is not None:
                    giro_bruto = val[1] - self.offset_centro
                elif val and len(val) > 0 and val[0] is not None:
                    giro_bruto = val[0] - self.offset_centro
                
                self.giro_suavizado = (self.giro_suavizado * 0.5) + (giro_bruto * 0.5)
                self.barra_giro.value = max(-5.0, min(5.0, self.giro_suavizado))
            except Exception:
                pass

        datos = {
            "steer": self.giro_suavizado,
            "accel": self.slider_acel.value,
            "brake": self.slider_freno.value,
            "clutch": self.embrague_presionado,
            "gear": self.marcha_actual if self.sistema_marchas_activo else 1
        }

        # Ejecución en segundo plano para evitar cualquier tipo de lag en los sliders
        threading.Thread(target=self._enviar_request_http, args=(datos,), daemon=True).start()

    def _enviar_request_http(self, datos):
        try:
            response = requests.post(f"http://{self.PC_IP}:{self.PC_PORT}/telemetry", json=datos, timeout=0.08)
            if response.status_code == 200:
                tele_pc = response.json()
                Clock.schedule_once(lambda dt: self.actualizar_interfaz_pc(tele_pc), 0)
        except Exception:
            Clock.schedule_once(lambda dt: self.actualizar_estado_desconectado(), 0)

    def actualizar_interfaz_pc(self, tele_pc):
        self.lbl_velocidad.text = str(int(tele_pc.get("speed", 0)))
        rpm_val = tele_pc.get("rpm", 0)
        self.slider_rpm.value = rpm_val
        
        if rpm_val > 6500:
            self.lbl_marcha_dash.color = (1, 0, 0, 1)
        else:
            self.lbl_marcha_dash.color = (1, 1, 0, 1)

        self.label_estado.text = "Conectado al PC OK"
        self.label_estado.color = (0, 1, 0, 1)

    def actualizar_estado_desconectado(self):
        self.label_estado.text = "Buscando servidor en PC..."
        self.label_estado.color = (1, 0.5, 0, 1)

class VolanteApp(App):
    def build(self):
        Window.size = (800, 480)
        return VolanteAppUI()

if __name__ == '__main__':
    VolanteApp().run()
