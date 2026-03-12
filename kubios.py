import network
from time import sleep
from umqtt.simple import MQTTClient
import ujson
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C

class Kubios:
    def __init__(self, oled=None):
       # Configure before use
        self.ssid = "YOUR_SSID"
        self.password = "YOUR_PASSWORD"
        self.broker_ip = "YOUR_BROKER_IP"
        self.broker_port = "YOUR_BROKER_PORT"
        
        
        self.oled = oled
        if not self.oled:
            self.oled = self.init_screen()
        
        
        
        self.connect_wlan()
        self.client = self.connect_mqtt()
        
        self.msg = None

    def init_screen(self):
        i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000)
        oled_w = 128
        oled_h = 64
        return SSD1306_I2C(oled_w, oled_h, i2c)

    def connect_wlan(self):
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(self.ssid, self.password)

        while not wlan.isconnected():
            print("Connecting to WiFi...")
            sleep(1)

        print("Connection successful. Pico IP:", wlan.ifconfig()[0])

    def connect_mqtt(self):
        try:
            client = MQTTClient("", self.broker_ip, self.broker_port)
            client.connect()
            client.set_callback(self.msg_callback)
            return client
        except:
            self.msg_handler("failed to connect mqtt")

    def send_message(self, data):
        json_data = self.convert_to_json(data)
        topic = "kubios-request"
        
        if self.client:
            try:
                self.msg_handler("sending data")
                self.client.publish(topic, json_data)
            except:
                self.oled.fill(0)
                
                self.msg_handler("failed to send the data")
                self.oled.show()
        
            self.client.subscribe("kubios-response")
            self.msg_handler("Waiting for response...")
            self.client.wait_msg()
        else:
            self.msg_handler("YOU LOST YOUR MQTT CLIENT")

    def convert_to_json(self, data_list):
    
        try:
            measurement = {
                "id": 123,
                "type": "RRI",
                "data": data_list,
                "analysis": {"type": "readiness"}
            }
            return ujson.dumps(measurement)
        except Exception as e:
            self.msg_handler(f"Error converting data to JSON: {e}")
            return None

    def msg_callback(self, topic, msg):
        try:
            self.msg = ujson.loads(msg)
        except Exception as e:
            self.msg_handler(f"Error processing received message: {e}")

    def print_results(self):
        self.oled.fill(0)
        self.oled.text(f"MEAN HR:{self.msg['data']['analysis']['mean_hr_bpm']}bpm", 0, 0)
        self.oled.text(f"MEAN PPI:{self.msg['data']['analysis']['mean_rr_ms']}ms", 0, 9)
        self.oled.text(f"RMSSD:{self.msg['data']['analysis']['rmssd_ms']}ms", 0, 18)
        self.oled.text(f"SDNN:{self.msg['data']['analysis']['sdnn_ms']}ms", 0, 27)
        self.oled.text(f"SNS:{self.msg['data']['analysis']['sns_index']}", 0, 36)
        self.oled.text(f"PNS:{self.msg['data']['analysis']['pns_index']}", 0, 45)
        self.oled.text("SW1 to Exit",0,54)
        self.oled.show()
        
    def process_and_display_data(self,data):
       # try:
        self.send_message(data)
        self.print_results()
       # except:
       #     self.msg_handler("Here lies our hopes and dreams")
                
    def msg_handler(self, message):
        self.oled.fill(0)
        words = message.split()
        
        max_line_length = 16 
        max_lines = 8  

        current_line = ""
        line_index = 0

        for word in words:
            if len(current_line) + len(word) + 1 <= max_line_length:
                if current_line:
                    current_line += " " 
                current_line += word
            else:
                
                self.oled.text(current_line, 0, line_index * 8)
                line_index += 1
                if line_index >= max_lines:
                    break  
                current_line = word 

        if current_line and line_index < max_lines:
            self.oled.text(current_line, 0, line_index * 8)

        self.oled.show()
