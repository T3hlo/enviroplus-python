#!/usr/bin/env python3

import time
import colorsys
import sys
from subprocess import check_output
import ST7735
import csv
import numpy as np
from datetime import datetime
import requests
import time

try:
    # Transitional fix for breaking change in LTR559
    from ltr559 import LTR559
    ltr559 = LTR559()
except ImportError:
    import ltr559

from bme280 import BME280
from pms5003 import PMS5003, ReadTimeoutError as pmsReadTimeoutError
from enviroplus import gas
from subprocess import PIPE, Popen, check_output
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from fonts.ttf import RobotoMedium as UserFont
import logging
import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(4,GPIO.OUT)

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("""all-in-one.py - Displays readings from all of Enviro plus' sensors

Press Ctrl+C to exit!

""")

# BME280 temperature/pressure/humidity sensor
bme280 = BME280()

# PMS5003 particulate sensor
pms5003 = PMS5003()

# Create ST7735 LCD display class
st7735 = ST7735.ST7735(
    port=0,
    cs=1,
    dc=9,
    backlight=12,
    rotation=270,
    spi_speed_hz=10000000
)

# Initialize display
st7735.begin()

WIDTH = st7735.width
HEIGHT = st7735.height

# Set up canvas and font
img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
font_size = 16
font = ImageFont.truetype(UserFont, font_size)

message = ""


# Display Raspberry Pi serial and Wi-Fi status on LCD
def display_status(time_since_update):
    wifi_status = "connected" if check_wifi() else "disconnected"
    text_colour = (255, 255, 255)
    back_colour = (0, 170, 170) if check_wifi() else (85, 15, 15)
    id = get_serial_number()
    message = "{}\nWi-Fi: {}\n{} min since update".format(id, wifi_status, round(time_since_update/60, 1))
    img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    size_x, size_y = draw.textsize(message, font)
    x = (WIDTH - size_x) / 2
    y = (HEIGHT / 2) - (size_y / 2)
    draw.rectangle((0, 0, 160, 80), back_colour)
    draw.text((x, y), message, font=font, fill=text_colour)
    st7735.display(img)
def display_luftdaten(resp):
    now = datetime.now()
    now.strftime('%Y-%m-%d %H:%M:%S')
    text_colour = (255, 255, 255)
    back_colour = (0, 102, 51) if resp else (85, 15, 15)
    if resp:
        p ='OK'
    else:
        p = 'failed'

    message = "Luftdaten\nUpload: {}\n{}".format(p, now.strftime('%Y-%m-%d %H:%M:%S'))
    img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    size_x, size_y = draw.textsize(message, font)
    x = (WIDTH - size_x) / 2
    y = (HEIGHT / 2) - (size_y / 2)
    draw.rectangle((0, 0, 160, 80), back_colour)
    draw.text((x, y), message, font=font, fill=text_colour)
    st7735.display(img)

def display_start():
    wifi_status = "connected" if check_wifi() else "disconnected"
    text_colour = (0, 0, 0)
    back_colour = (255, 255, 0)
    id = get_serial_number()
    message = "System waking up.\nWi-Fi: {}\nPlease wait...".format(wifi_status)
    img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    size_x, size_y = draw.textsize(message, font)
    x = (WIDTH - size_x) / 2
    y = (HEIGHT / 2) - (size_y / 2)
    draw.rectangle((0, 0, 160, 80), back_colour)
    draw.text((x, y), message, font=font, fill=text_colour)
    st7735.display(img)


def owl():
    back_colour = (0, 0, 0)
    text_colour = (255, 255, 0)
    message = "      .___,\n___('v')___\n  '''-\._./-''\n        ^ ^  "
    img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    draw = ImageDraw.Draw(img)
    size_x, size_y = draw.textsize(message, font)
    x = (WIDTH - size_x) / 2
    y = (HEIGHT / 2) - (size_y / 2)
    draw.rectangle((0, 0, 160, 80), back_colour)
    draw.text((x, y), message, font=font, fill=text_colour)
    st7735.display(img)


# Displays data and text on the 0.96" LCD
def display_text(variable, data, unit):
    # Maintain length of list
    values[variable] = values[variable][1:] + [data]
    # Scale the values for the variable between 0 and 1
    vmin = min(values[variable])
    vmax = max(values[variable])
    colours = [(v - vmin + 1) / (vmax - vmin + 1) for v in values[variable]]
    # Format the variable name and value
    message = "{}: {:.1f} {}".format(variable[:4], data, unit)
    logging.info(message)
    draw.rectangle((0, 0, WIDTH, HEIGHT), (255, 255, 255))
    for i in range(len(colours)):
        # Convert the values to colours from red to blue
        colour = (1.0 - colours[i]) * 0.6
        r, g, b = [int(x * 255.0) for x in colorsys.hsv_to_rgb(colour, 1.0, 1.0)]
        # Draw a 1-pixel wide rectangle of colour
        draw.rectangle((i, top_pos, i + 1, HEIGHT), (r, g, b))
        # Draw a line graph in black
        line_y = HEIGHT - (top_pos + (colours[i] * (HEIGHT - top_pos))) + top_pos
        draw.rectangle((i, line_y, i + 1, line_y + 1), (0, 0, 0))
    # Write the text at the top in black
    draw.text((0, 0), message, font=font, fill=(0, 0, 0))
    st7735.display(img)

# Get Raspberry Pi serial number to use as ID
def get_serial_number():
    with open('/proc/cpuinfo', 'r') as f:
        for line in f:
            if line[0:6] == 'Serial':
                return line.split(":")[1].strip()


# Check for Wi-Fi connection
# Ping google
def check_wifi():
    try:
        check_output(["ping", "-c", "1", "google.com"])
        return True
    except:
        return False

# Get the temperature of the CPU for compensation
def get_cpu_temperature():
    process = Popen(['vcgencmd', 'measure_temp'], stdout=PIPE, universal_newlines=True)
    output, _error = process.communicate()
    return float(output[output.index('=') + 1:output.rindex("'")])


def save_data(data, message, output_dir='/home/pi/datasets/'):
    print(message)

    with open(output_dir + 'sensor_data.csv', 'w') as f1:
        writer = csv.writer(f1, delimiter=',')  # lineterminator='\n',
        for row in data:
            writer.writerow(row)
    return [], time.time()


# Tuning factor for compensation. Decrease this number to adjust the
# temperature down, and increase to adjust up
factor = 1.3

# Raspberry Pi ID to send to Luftdaten
id = "raspi-" + get_serial_number()


cpu_temps = [get_cpu_temperature()] * 5

delay = 0.5  # Debounce the proximity tap
mode = 0  # The starting mode
last_page = 0
light = 1

# Create a values dict to store the data
variables = ["temperature",
             "pressure",
             "humidity",
             "light",
             "oxidised",
             "reduced",
             "nh3",
             "pm1",
             "pm25",
             "pm10",
             "wifi"]
#
# variables = ["temperature",
#              "pressure",
#              "humidity",
#              "light",
#              "oxidised",
#              "reduced",
#              "nh3",
#              "wifi"]

def sensor_querry(cpu_temps):
    '''
    Get data from all sensors.
    '''

    # get timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d, %H:%M:%S")  # current date and time

    # temperature
    cpu_temp = get_cpu_temperature()
    # Smooth out with some averaging to decrease jitter
    cpu_temps = cpu_temps[1:] + [cpu_temp]
    avg_cpu_temp = sum(cpu_temps) / float(len(cpu_temps))
    raw_temp = bme280.get_temperature()
    temp = raw_temp - ((avg_cpu_temp - raw_temp) / factor)

    # pressure
    pres = bme280.get_pressure()

    #humidity
    humi = bme280.get_humidity()

    # light
    # if proximity < 10:
    #     light = ltr559.get_lux()
    # else:
    #     light = 1

    # oxidised gas
    oxi = gas.read_all()
    oxi = oxi.oxidising / 1000

    # reduced gas
    redu = gas.read_all()
    redu = redu.reducing / 1000

    # NH3
    nh3 = gas.read_all()
    nh3 = nh3.nh3 / 1000

    # PM1
    try:
        pm1 = pms5003.read()
    except pmsReadTimeoutError:
        logging.warning("Failed to read PMS5003")
    else:
        pm1 = float(pm1.pm_ug_per_m3(1.0))

    # PM2.5
    try:
        pm25 = pms5003.read()
    except pmsReadTimeoutError:
        logging.warning("Failed to read PMS5003")
    else:
        pm25 = float(pm25.pm_ug_per_m3(2.5))

    # PM10
    try:
        pm10 = pms5003.read()
    except pmsReadTimeoutError:
        logging.warning("Failed to read PMS5003")
    else:
        pm10 = float(pm10.pm_ug_per_m3(10))

    return timestamp, temp, pres, humi, light, oxi, redu, nh3, pm1, pm25, pm10, cpu_temps
    #return timestamp, temp, pres, humi, light, oxi, redu, nh3, cpu_temps

def send_to_luftdaten(values, id):
    pm_values = dict(i for i in values.items() if i[0].startswith("P"))
    temp_values = dict(i for i in values.items() if not i[0].startswith("P"))

    pm_values_json = [{"value_type": key, "value": val} for key, val in pm_values.items()]
    temp_values_json = [{"value_type": key, "value": val} for key, val in temp_values.items()]

    resp_1 = requests.post(
        "https://api.luftdaten.info/v1/push-sensor-data/",
        json={
            "software_version": "enviro-plus 0.0.1",
            "sensordatavalues": pm_values_json
        },
        headers={
            "X-PIN": "1",
            "X-Sensor": id,
            "Content-Type": "application/json",
            "cache-control": "no-cache"
        }
    )

    resp_2 = requests.post(
        "https://api.luftdaten.info/v1/push-sensor-data/",
        json={
            "software_version": "enviro-plus 0.0.1",
            "sensordatavalues": temp_values_json
        },
        headers={
            "X-PIN": "11",
            "X-Sensor": id,
            "Content-Type": "application/json",
            "cache-control": "no-cache"
        }
    )

    if resp_1.ok and resp_2.ok:
        return True
    else:
        return False


values = {}

for v in variables:
    values[v] = [1] * WIDTH

data = []
start_time = time.time()

time_since_update = 0
update_time = time.time()

display_start()
time.sleep(5)
owl()
time.sleep(10)

def flash_LED(seconds):
    display_status(time_since_update)
    GPIO.output(4, GPIO.HIGH)
    time.sleep(seconds)
    GPIO.output(4, GPIO.LOW)


# The main loop
try:
    while True:
        try:
            #proximity = ltr559.get_proximity()

            # Querry all sensors:
            timestamp, temp, pres, humi, light, oxi, redu, nh3, pm1, pm25, pm10, cpu_temps = sensor_querry(cpu_temps)
            data.append(np.array([timestamp, temp, pres, humi, light, oxi, redu, nh3, pm1, pm25, pm10]))

            #timestamp, temp, pres, humi, light, oxi, redu, nh3, cpu_temps = sensor_querry(cpu_temps)
            #data.append(np.array([timestamp, temp, pres, humi, light, oxi, redu, nh3]))

            # Send to luftdaten
            time_since_update = time.time() - update_time

            if time_since_update > 145:
                to_send = {}
                to_send["temperature"] = "{:.2f}".format(temp)
                to_send["pressure"] = "{:.2f}".format(pres)
                to_send["humidity"] = "{:.2f}".format(humi)
                to_send["P2"] = str(pm25)
                to_send["P1"] = str(pm10)

                resp = send_to_luftdaten(to_send, id)
                update_time = time.time()
                print("Response: {}\n".format("ok" if resp else "failed"))
                display_luftdaten(resp)
                for i in range(0,3):
                    flash_LED(0.1)

            else:
                display_status(time_since_update)
                flash_LED(0.1)


            # If the proximity crosses the threshold, toggle the mode
            # if proximity > 1500 and time.time() - last_page > delay:
            #     mode += 1
            #     mode %= len(variables)
            #     last_page = time.time()



            if (time.time()-start_time)/60 >180:
                data, start_time = save_data(data, 'Scheduled data saving!')
                for i in range(0,5):
                    flash_LED(0.1)
        except Exception as e:
            print(e)



# Exit cleanly
except KeyboardInterrupt:
    #data, start_time = save_data(data, 'Saving data after exception!')
    sys.exit()
