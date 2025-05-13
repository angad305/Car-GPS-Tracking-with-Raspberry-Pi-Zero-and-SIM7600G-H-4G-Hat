import serial
import time
import Adafruit_SSD1306
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
import subprocess
import requests
import sys
import logging
import pytz
from datetime import datetime


########### USER INPUT BELOW ##################

# Set up Telegram bot
TOKEN = '[TOKEN]'
chat_id = '[CHAT ID]'

#Trac Car Server (https://www.traccar.org/)
TRACCAR_URL = "[TRAC CAR URL]"

#Send GPS Position after how many seconds
SEND_POSTN_EVERY = 3

#DEVICE ID FOR TRAC CAR
CAR_UNIQUE_ID = "my_car_name"


###############################################

# Set up logging
logging.basicConfig(filename='/home/user/car.log', 
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize OLED display
disp = Adafruit_SSD1306.SSD1306_128_32(rst=None)
disp.begin()
disp.clear()
disp.display()

# Create image buffer for OLED
width = disp.width
height = disp.height
image = Image.new('1', (width, height))
draw = ImageDraw.Draw(image)

# Load a TTF font that supports Unicode
font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)

# Define tick and cross symbols for OLED display
tick_symbol = '\u2714'  # Unicode for checkmark (✔)
cross_symbol = '\u2718'  # Unicode for cross (✘)


def get_current_time_ist():
    # Define the IST timezone
    ist_timezone = pytz.timezone('Asia/Kolkata')
    # Get the current time in UTC and convert it to IST
    ist_time = datetime.now(ist_timezone)
    # Return the time formatted as 'HH:MM:SS hrs on dd/mmm/yyyy'
    return ist_time.strftime('%H:%M:%S') + " hrs on " + ist_time.strftime('%d/%b/%Y')

def send_telegram_message(message):
    # Append the current time in IST to the message
    current_time_ist = get_current_time_ist()
    full_message = f"{message}\nTime (IST): {current_time_ist}"
    
    # Send the message via Telegram
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={chat_id}&text={full_message}"
    response = requests.get(url)
    print(f"Telegram API response: {response.text}")
    print(f"Status code: {response.status_code}")
    if response.status_code == 200:
        print('Notification sent successfully')
    else:
        print('Failed to send notification')

def update_oled_display(network_status, gps_status):
    draw.rectangle((0, 0, width, height), outline=0, fill=0)  # Clear display
    network_display = f"Network : {'ON' if network_status else cross_symbol}"
    gps_display = f"GPS     : {'ON' if gps_status else cross_symbol}"
    
    # Show network and GPS status on OLED
    draw.text((0, 0), network_display, font=font, fill=255)
    draw.text((0, 18), gps_display, font=font, fill=255)
    
    # Display the image
    disp.image(image)
    disp.display()

def start_lte_connection():
    try:
        subprocess.run(["sudo", "/usr/local/bin/start-lte"], check=True)
        logging.info("LTE connection started successfully")
    except subprocess.CalledProcessError:
        logging.error("Failed to start LTE connection")
        sys.exit(1)

def check_internet():
    try:
        requests.get("http://www.google.com", timeout=5)
        return True
    except requests.ConnectionError:
        return False
    
def restart_tailscaled():
    try:
        subprocess.run(["sudo", "systemctl", "restart", "tailscaled"], check=True)
        logging.info("Tailscaled restarted successfully")
    except subprocess.CalledProcessError:
        logging.error("Failed to restart tailscaled")

def send_at(ser, command, back, timeout):
    rec_buff = ''
    ser.write((command + '\r\n').encode())
    time.sleep(timeout)
    if ser.in_waiting:
        time.sleep(0.01)
        rec_buff = ser.read(ser.in_waiting).decode()
    if back not in rec_buff:
        logging.error(f"{command} ERROR")
        logging.error(f"{command} back:\t{rec_buff}")
        return None  # Return None explicitly on error
    else:
        logging.debug(rec_buff)
        return rec_buff  # Return the received buffer if successful

def parse_gps_data(gps_info):
    parts = gps_info.split(',')
    if len(parts) < 8:
        return None
    
    lat = float(parts[0][:2]) + float(parts[0][2:]) / 60
    lon = float(parts[2][:3]) + float(parts[2][3:]) / 60
    if parts[1] == 'S':
        lat = -lat
    if parts[3] == 'W':
        lon = -lon
    
    return {
        "lat": lat,
        "lon": lon,
        "alt": float(parts[6]),
        "speed": float(parts[7]) * 1.852,  # Convert knots to km/h
        "timestamp": f"20{parts[4][4:6]}-{parts[4][2:4]}-{parts[4][:2]}T{parts[5][:2]}:{parts[5][2:4]}:{parts[5][4:6]}Z"
    }

def get_gps_position(ser):
    logging.info('Start GPS session...')
    
    # Check if GPS is already running
    gps_status = send_at(ser, 'AT+CGPS?', '+CGPS: ', 1)
    if gps_status and '+CGPS: 1' in gps_status:
        logging.info("GPS already running.")
    else:
        # Start the GPS session only if not already running
        if not send_at(ser, 'AT+CGPS=1', 'OK', 1):
            logging.error("Failed to start GPS")
            return None

    time.sleep(2)  # Give time for GPS to initialize

    for _ in range(10):  # Try up to 10 times to get GPS info
        answer = send_at(ser, 'AT+CGPSINFO', '+CGPSINFO: ', 1)
        if answer is None:  # Check if the result is None
            logging.error('Failed to send AT+CGPSINFO command')
            continue

        if ',,,,,,' in answer:
            logging.warning('GPS is not ready')
        else:
            logging.info(f'GPS Position: {answer}')
            gps_info = answer.split(': ')[1].strip()
            return parse_gps_data(gps_info)  # Ensure this parses correctly

        time.sleep(0.5)
    
    logging.error('Failed to get valid GPS data after multiple attempts')
    return None

def send_data_to_traccar(data):
    url = TRACCAR_URL
    
    # Assuming data contains the following fields: lat, lon, speed, altitude, bearing, and battery level
    params = {
        "id": CAR_UNIQUE_ID,               # Device ID
        "lat": data['lat'],             # Latitude
        "lon": data['lon'],             # Longitude
        "timestamp": int(time.time()),  # Current timestamp
        "altitude": data['alt'],        # Altitude
        "speed": round(data['speed'], 2),   # Speed, rounded to 2 decimal places
        "bearing": data.get('bearing', 0),   # Bearing, default to 0 if not provided
        "batt": data.get('batt', 100)   # Battery level, default to 100 if not provided
    }
    
    try:
        response = requests.get(url, params=params)
        return response.status_code == 200
    except requests.RequestException:
        return False        

def print_results(gps_data):
    print("\n--- GPS Data ---")
    if gps_data:
        print(f"Timestamp: {gps_data['timestamp']}")
        print(f"Latitude: {gps_data['lat']:.6f}°")
        print(f"Longitude: {gps_data['lon']:.6f}°")
        print(f"Altitude: {gps_data['alt']} meters")
        print(f"Speed: {gps_data['speed']:.2f} km/h")
    else:
        print("No valid GPS data received.")
    print("----------------\n")

def stop_modem_manager():
    try:
        print("Stopping ModemManager service...")
        logging.info("Stopping ModemManager service...")
        subprocess.run(["sudo", "systemctl", "stop", "ModemManager"], check=True)
        print("ModemManager service stopped successfully")
        logging.info("ModemManager service stopped successfully")
    except subprocess.CalledProcessError as e:
        print(f"Failed to stop ModemManager service: {e}")
        logging.error(f"Failed to stop ModemManager service: {e}")
        sys.exit(1)

def main():
    prev_network_status = None
    prev_gps_status = None
    telegram_notification_sent = False  # flag to ensure one-time notification

    while True:  # Outer infinite loop
        try:
            stop_modem_manager()
            print("Starting LTE connection...")
            logging.info("Starting LTE connection...")
            start_lte_connection()

            internet_retry_count = 0
            network_status = False  # Initialize as False
            while not check_internet():
                print(f"Waiting for internet connection... (Attempt {internet_retry_count + 1})")
                logging.info(f"Waiting for internet connection... (Attempt {internet_retry_count + 1})")
                network_status = False
                time.sleep(5)
                internet_retry_count += 1
                if internet_retry_count >= 12:  # 1 minute of retries
                    raise Exception("Failed to establish internet connection after 1 minute")

            print("Internet connection established. Restarting tailscaled...")
            logging.info("Internet connection established. Restarting tailscaled...")
            restart_tailscaled()
            network_status = True  # Set network status to True

            # Send Telegram notification only once
            if not telegram_notification_sent:
                send_telegram_message("Baleno Started...")
                telegram_notification_sent = True  # Prevent further notifications

            # Only update OLED if network status has changed
            if network_status != prev_network_status:
                update_oled_display(network_status, prev_gps_status)
                prev_network_status = network_status

            print("Starting GPS data collection...")
            logging.info("Starting GPS data collection...")
            gps_status = False  # Initialize as False

            ser = None
            try:
                ser = serial.Serial('/dev/ttyUSB2', 115200, timeout=1)
                print("GPS Module initialized.")
                logging.info("GPS Module initialized.")
            except serial.SerialException as e:
                print(f"Failed to initialize serial port: {e}")
                logging.error(f"Failed to initialize serial port: {e}")
                raise  # Re-raise the exception to be caught by the outer try-except

            gps_failure_count = 0
            while True:  # Inner loop for GPS data collection
                try:
                    gps_data = get_gps_position(ser)
                    if gps_data:
                        print_results(gps_data)
                        gps_status = True  # Set GPS status to True
                        logging.info(f"GPS Data: {gps_data}")
                        # Send data to Traccar server
                        if send_data_to_traccar(gps_data):
                            print("Data sent successfully to Traccar server")
                            logging.info("Data sent successfully to Traccar server")
                            gps_failure_count = 0  # Reset failure count on success
                        else:
                            print("Failed to send data to Traccar server")
                            logging.error("Failed to send data to Traccar server")
                            gps_failure_count += 1

                    else:
                        print("No valid GPS data received.")
                        gps_status = False  # Set GPS status to False
                        logging.warning("No valid GPS data received.")
                        gps_failure_count += 1

                    # Update OLED display only if network or GPS status has changed
                    if network_status != prev_network_status or gps_status != prev_gps_status:
                        update_oled_display(network_status, gps_status)
                        prev_network_status = network_status
                        prev_gps_status = gps_status

                    if gps_failure_count >= 20:  # Retry indefinitely
                        logging.warning("Persistent GPS failure, continuing to retry indefinitely.")
                        gps_failure_count = 0  # Reset failure count but keep retrying

                    print("Waiting for 3 seconds before next reading...")
                    time.sleep(SEND_POSTN_EVERY)

                except (serial.SerialException, requests.RequestException) as e:
                    print(f"Error in GPS data collection or server communication: {e}")
                    logging.error(f"Error in GPS data collection or server communication: {e}")
                    time.sleep(3)

        except Exception as e:
            print(f"An error occurred in the main loop: {e}")
            logging.error(f"An error occurred in the main loop: {e}")
            if ser:
                ser.close()
            print("Restarting the entire process in 60 seconds...")
            logging.info("Restarting the entire process in 60 seconds...")
            update_oled_display(False, False)  # Both Network and GPS OFF
            time.sleep(60)


if __name__ == "__main__":
    main()