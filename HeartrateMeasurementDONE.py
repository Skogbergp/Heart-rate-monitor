import time
from machine import Pin, I2C, ADC
from ssd1306 import SSD1306_I2C
from piotimer import Piotimer

# Hardware configuration
sw0 = Pin(9, Pin.IN, Pin.PULL_UP)
sw1 = Pin(8, Pin.IN, Pin.PULL_UP)
sw2 = Pin(7, Pin.IN, Pin.PULL_UP)
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
    global all_beat_timestamps, is_beat_detected, avg_bpm, avg_hrv, measurement_start_time, is_warming_up, measurement_started

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
        timestamp = time.ticks_ms()
        all_beat_timestamps.append(timestamp)

        # Update BPM and HRV
        avg_bpm = calculate_bpm(all_beat_timestamps)
        avg_hrv = calculate_hrv(all_beat_timestamps)

    elif current_value < threshold_off and is_beat_detected:
        is_beat_detected = False

    # Refresh display with BPM and HRV
    update_display(avg_bpm, avg_hrv, is_beat_detected)

    if sw1.value() == 0:
        stop_measurement()


def start_measurement():
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
    global avg_bpm, avg_hrv

    # Calculate BPM and HRV using all recorded beats
    avg_bpm = calculate_bpm(all_beat_timestamps)
    avg_hrv = calculate_hrv(all_beat_timestamps)

    # Display the results
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

    # Wait for SW1 press to return to the main menu
    while sw1.value() == 1:
        time.sleep(0.1)  # Debounce


def main():
    global is_warming_up, measurement_started

    oled_display.fill(0)
    oled_display.text("Press SW1 to", 20, 10, 1)
    oled_display.text("Start", 50, 30, 1)
    oled_display.text("Measurement", 30, 50, 1)
    oled_display.show()

    while True:
        if sw1.value() == 0:
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

main()

