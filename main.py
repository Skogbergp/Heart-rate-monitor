import time
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from piotimer import Piotimer
import math

import micropython
micropython.alloc_emergency_exception_buf(200)

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
  
  


# Hardware configuration
sw1 = Pin(8, Pin.IN, Pin.PULL_UP)
i2c_bus = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000)
screen_width = 128
screen_height = 64
oled_display = SSD1306_I2C(screen_width, screen_height, i2c_bus)
pulse_sensor = ADC(26)

# Constants
HISTORY_LIMIT = 250
MEASUREMENT_DURATION = 30  # Timeout in seconds
WARMUP_PERIOD = 5  # Number of seconds to allow the sensor to stabilize

# Variables
is_measuring = False
sensor_data = [0] * HISTORY_LIMIT  # Pre-allocated buffer
data_index = 0
is_beat_detected = False
previous_y = 32
sensor_min, sensor_max = 0, 65535  # ADC range
current_value = 0
timer = None
avg_bpm = None
all_beat_timestamps = []  # Store all beat timestamps
avg_hrv = None
measurement_start_time = 0
warmup_start_time = 0
measurement_started = False
is_warming_up = False
mode = 0
previous_timestamp = 0
unfiltered_timestamps = []

# Functions
def calculate_bpm(beat_timestamps):
    if len(beat_timestamps) > 1:
        total_time = (beat_timestamps[-1] - beat_timestamps[0]) / 1000  # Convert to seconds
        beat_count = len(beat_timestamps) - 1
        return (beat_count / total_time) * 60  # BPM calculation
    return None


def calculate_hrv(beat_timestamps):
    if len(beat_timestamps) > 1:
        rr_intervals = [beat_timestamps[i] - beat_timestamps[i - 1] for i in range(1, len(beat_timestamps))]
        if rr_intervals:
            avg_rr = sum(rr_intervals) / len(rr_intervals)  # Average R-R interval
            return avg_rr / 1000  # Convert ms to s
    return None


def update_display(bpm, hrv, beat_detected):
    global previous_y, sensor_min, sensor_max
    oled_display.scroll(-1, 0)

    # Clear previous BPM and HRV values
    oled_display.fill_rect(0, 0, 128, 20, 0)  # Clear the area for BPM and HRV display
    
    # Update display graph
    if sensor_max - sensor_min > 0:
        y_position = 40 - int(16 * (current_value - sensor_min) / (sensor_max - sensor_min))  # Graph starts from y = 40
        oled_display.line(125, previous_y, 126, y_position, 1)
        previous_y = y_position

    # Display BPM and HRV
    if bpm:
        oled_display.text(f"Avg BPM: {int(bpm)}", 0, 0)
    if hrv:
        oled_display.text(f"HRV: {hrv:.2f}s", 0, 10)
    
    oled_display.show()


def timer_callback(timer):
    global sensor_data, data_index, current_value, sensor_min, sensor_max

    # Read sensor and store in buffer
    current_value = pulse_sensor.read_u16()
    sensor_data[data_index] = current_value
    data_index = (data_index + 1) % HISTORY_LIMIT

    # Update min and max
    sensor_min = min(sensor_data)
    sensor_max = max(sensor_data)


def process_heart_rate():
    #print ("process heart rate")
    global all_beat_timestamps, is_beat_detected, avg_bpm, avg_hrv, measurement_start_time, is_warming_up, measurement_started, previous_timestamp
    
    
    
    if is_warming_up:
        return  # Skip heart rate processing during warm-up

    # Start measurement after warm-up period is over
    if not measurement_started:
        measurement_started = True
        measurement_start_time = time.ticks_ms()  # Set measurement start time after warm-up
        print("Measurement started...")  # Debug

    # Stop measurement after 30s
    if (time.ticks_ms() - measurement_start_time) > MEASUREMENT_DURATION * 1000:
        stop_measurement()
        return

    # Detect beats based on thresholds
    threshold_on = (sensor_min + sensor_max * 3) // 4
    threshold_off = (sensor_min + sensor_max) // 2

    if current_value > threshold_on and not is_beat_detected:
        is_beat_detected = True
        
        
        current_timestamp = time.ticks_ms()
        if not previous_timestamp == 0:
            timestamp = current_timestamp - previous_timestamp
            all_beat_timestamps.append(timestamp)
            unfiltered_timestamps.append(current_timestamp)
        previous_timestamp = current_timestamp
        
        # Update BPM and HRV
        avg_bpm = calculate_bpm(unfiltered_timestamps)
        avg_hrv = calculate_hrv(unfiltered_timestamps)

    elif current_value < threshold_off and is_beat_detected:
        is_beat_detected = False

    # Refresh display with BPM and HRV
    update_display(avg_bpm, avg_hrv, is_beat_detected)

    if sw1.value() == 0:
        stop_measurement()


def start_measurement():
    print("start measurement")
    global is_measuring, timer, warmup_start_time, is_warming_up, measurement_started
    is_measuring = True
    warmup_start_time = time.ticks_ms()  # Record the time when warm-up starts
    is_warming_up = True 
    measurement_started = False 
    oled_display.fill(0)
    oled_display.text("Measuring...", 15, 25, 1)
    oled_display.show()

    # Start timer for sensor readings
    timer = Piotimer(freq=250, callback=timer_callback)


def stop_measurement():
    global is_measuring, timer
    is_measuring = False
    if timer:
        timer.deinit()
    oled_display.fill(0)
    oled_display.text("Measurement", 20, 20, 1)
    oled_display.text("Stopped", 35, 40, 1)
    oled_display.show()
    time.sleep(2)
    display_results()


def display_results():
    global avg_bpm, avg_hrv, mode, all_beat_timestamps, unflitered_timestamps

    # Calculate BPM and HRV using all recorded beats
    avg_bpm = calculate_bpm(unfiltered_timestamps)
    avg_hrv = calculate_hrv(unfiltered_timestamps)
    
    rr_intervals = [all_beat_timestamps[i] - all_beat_timestamps[i - 1] for i in range(1, len(all_beat_timestamps))]
    differences_squared = [diff ** 2 for diff in rr_intervals]
    rmssd = math.sqrt(sum(differences_squared) / (len(all_beat_timestamps) - 1))
    
    print(all_beat_timestamps)
    
    n = len(all_beat_timestamps)
    if not (n < 2):
        
        mean = sum(all_beat_timestamps) / n
        sdnn = sum((x - mean) ** 2 for x in all_beat_timestamps) / (n - 1)
        sdnn = sdnn ** 0.5
    
    print(mode)
    
    # Display the results
    
    if mode == 1:
        oled_display.fill(0)
        oled_display.text("SW1 to exit", 10, 50, 1)
        if avg_bpm:
            oled_display.text(f"Avg BPM: {avg_bpm:.2f}", 10, 10, 1)
        else:
            oled_display.text("No BPM", 10, 10, 1)
        if avg_hrv:
            oled_display.text(f"HRV: {avg_hrv:.2f}s", 10, 30, 1)
        else:
            oled_display.text("No HRV", 10, 30, 1)
        oled_display.show()
        
        
        
    if mode == 2:
        
        oled_display.fill(0)
        
        if avg_bpm:
            mean_ppi = 60000 / avg_bpm 
        oled_display.fill(0)
        oled_display.text("SW1 to exit", 10, 50, 1)
        if avg_bpm:
            oled_display.text(f"Mean HR: {avg_bpm:.2f}", 10, 10, 1)
        else:
            oled_display.text("No HR", 10, 10, 1)
        if avg_bpm:
            oled_display.text(f"PPI: {mean_ppi:.2f}", 10, 20, 1)
        else:
            oled_display.text("No PPI", 10, 20, 1)
        
        if avg_hrv:
            oled_display.text(f"RMSSD: {rmssd:.2f}ms", 10, 30, 1)
        else:
            oled_display.text("No RMSSD", 10, 30, 1)
        
        if sdnn:
            oled_display.text(f"SDNN: {sdnn:.2f}ms", 10, 40, 1)
        else:
            oled_display.text("No SDNN", 10, 40, 1)
        
        oled_display.show()
    
    if mode == 3:
        
        kubios = Kubios(oled_display)
        kubios.process_and_display_data(all_beat_timestamps)
        
        
    #    oled_display.fill(0)
    
     #   oled_display.show()
    
    # Wait for SW1 press to return to the main menu
    while sw1.value() == 1:
        time.sleep(0.1)# Debounce
    menu()
        

def main(duration):
    global is_warming_up, measurement_started, button_handler
    global MEASUREMENT_DURATION
    
    print("main")
    
    MEASUREMENT_DURATION = duration
    is_measuring = 1
    
    time.sleep(0.2)  # Debounce
    start_measurement()
    while is_measuring:
        # Check if warm-up period is over
        if is_warming_up and (time.ticks_ms() - warmup_start_time) >= WARMUP_PERIOD * 1000:
            is_warming_up = False  # Warm-up period is complete
            print("Warm-up complete, starting measurement...")  # Debug
                # Process heart rate after warm-up
        process_heart_rate()
        time.sleep(0.01)
    oled_display.fill(0)
    oled_display.text("Press SW1 to", 20, 10, 1)
    oled_display.text("Start", 50, 30, 1)
    oled_display.text("Measurement", 30, 50, 1)
    oled_display.show()
    time.sleep(2)
            
    while sw1.value() == 1:
        time.wait(0.000000001)
        
                
            
###########################################################################################

#global position
position = 1

button = Pin(12, mode = Pin.IN, pull = Pin.PULL_UP)
pressed = False



def button_handler(pin):
    global pressed, is_measuring
    pressed = True
    if is_measuring == False:
        #is_measuring = True
        
        if position == 1:
            rot.fifo.put(5)
        if position == 2:
            rot.fifo.put(6)
        if position == 3:
            rot.fifo.put(7)
        time.sleep(0.1)

button.irq(handler = button_handler, trigger = Pin.IRQ_FALLING, hard = True)

from fifo import Fifo
class Encoder:
    def __init__(self, rot_a, rot_b):
        self.a = Pin(rot_a, mode = Pin.IN)
        self.b = Pin(rot_b, mode = Pin.IN)
        self.fifo = Fifo(30, typecode = 'i')
        self.a.irq(handler = self.handler, trigger = Pin.IRQ_RISING, hard = True)
    def handler(self, pin):
        if self.b():
            self.fifo.put(-1)
        else:
            self.fifo.put(1)

rot = Encoder(10, 11)
def menu():
    
    global is_measuring
    global pressed
    global position
    global mode
    
    oled_display.fill(0)
    
        
    oled_display.text("HR measurement", 0, 0, 1)

    oled_display.text("HRV analysis", 0, 20, 1)

    oled_display.text("Kubios", 0, 40, 1)

    oled_display.fill_rect(115, ((position - 1) * 20) + 1, 4, 4, 1)

    oled_display.show()
    
    while is_measuring == False:
    
        
        
        if pressed:
            pressed = False
    
 
        
        
        while rot.fifo.has_data():
            
            oled_display.fill(0)
    
        
            oled_display.text("HR measurement", 0, 0, 1)
        
            oled_display.text("HRV analysis", 0, 20, 1)
        
            oled_display.text("Kubios", 0, 40, 1)
    
            oled_display.fill_rect(115, ((position - 1) * 20) + 1, 4, 4, 1)
    
            oled_display.show()
            
            rotation = rot.fifo.get()
            if rotation == 1 and position < 3:
                position += 1
            if rotation == -1 and position > 1:
                position -= 1
            
            
            
            if rotation == 5:
                
                print("A")
                
                while rot.fifo.has_data():
                    rotation = rot.fifo.get()
                mode = 1
                main(15)
            
            elif rotation == 6:
                
                print("B")
                
                while rot.fifo.has_data():
                    rotation = rot.fifo.get()
                
                mode = 2
                main(30)
                
            elif rotation == 7:
                
                while rot.fifo.has_data():
                    rotation = rot.fifo.get()
                
                mode = 3
                main(30)

menu()
